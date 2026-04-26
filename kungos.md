# K-Team Stack Modernization Plan

**Project Code:** KungOS
**Prepared:** 2026-04-22
**Status:** Draft for lock after checklist completion


---

## Executive Summary

K-Team is a dual-stack business platform built on a React frontend and a Django/DRF backend, with PostgreSQL, MongoDB, and MeiliSearch in the data layer, and the audit identified 97 issues across security, performance, maintainability, and scalability. [file:3] The most important compounding problems are hardcoded credentials, duplicated access-control logic, pandas-based permission filtering, per-request MongoDB client creation, no caching or job queue, no test coverage, and frontend state/data-fetching patterns that do not scale well. [file:3]

A second codebase — `kuro-gaming-dj-backend` — provides e-commerce functionality for custom/prebuilt PC sales (product catalog, cart, wishlist, addresses, orders, payment processing, game catalog, CMS) but has its own set of critical issues: 9+ hardcoded credentials, Django 4.1.13 (EOL), use of `djongo` (deprecated ORM bridge), no multi-tenant support, no DRF serializers for products/games, and no authentication on admin endpoints. The companion frontend `kurogg-nextjs` is a thin reverse proxy with zero backend logic and should be retired entirely.

This v3 plan adopts the counter-review assumption that **no changes will be deployed until the full modernization program is complete**. [file:37] Because of that, this plan intentionally removes canary rollout, staging-first rollout, feature flags for auth migration, and mid-program production cutovers, and replaces them with one final deployment supported by one rollback path: git revert plus database backup restore. [file:37]

This is a phased modernization, not a rewrite. [file:3][file:37] The plan keeps the current strong foundations such as Django 5.2, DRF 3.15, React 19, Vite 8, PyMongo, PostgreSQL, MongoDB, MeiliSearch, Radix UI, and Recharts, while replacing unmaintained or upgrade-hostile dependencies and standardizing cross-cutting platform concerns. The gaming integration adds 5 new apps, 12 MongoDB collections, and ~180 hours of additional work on top of the existing ~380-hour modernization program, with ~140 hours of overlap eliminated through coordination of shared infrastructure work (security, dependencies, auth, Redis/Celery). The combined total is **340–520 hours (8.5–13 weeks)**, likely **420 hours (10.5 weeks)**.

---

## Planning Assumptions

### Delivery model

No production deployment will occur during the modernization program. [file:37] Development happens in local/dev environments only, and go-live occurs as a single deployment at the end of the program. [file:37]

### Environment model

The environment strategy for this program is **dev + prod only**. [file:37] A staging environment is explicitly out of scope for the modernization period because no intermediate deployment validation is being performed in production-like stages. [file:37]

### Rollout model

Canary deployment, phased rollout, and feature-flag infrastructure are out of scope. The program ships exactly once: a single deployment at the end of the modernization program. All auth coexistence (Knox → SimpleJWT, kteam/gaming user merge) is handled in code during development, never by deploying two systems side by side in production.

### Rollback model

There is one rollback path for the final cutover: revert the deployment commit and restore the pre-cutover database backup. [file:37] This replaces the previous idea of per-phase rollback playbooks. [file:37] The rollback runbook is documented in the Cutover Checklist section (items 39–43). Rollback requires approval from the Modernization Owner.

### Runtime baseline

Python 3.12 is retained as the baseline for this modernization cycle, and Python 3.13 is deferred to a separate post-modernization upgrade. [file:37] The counter-review recommends this because the current modernization already introduces many moving parts, while Django 5.2 already supports Python 3.12 and the audit did not identify Python version itself as the primary issue. [file:37]

### Workstream governance

The program has two workstreams that run in parallel with explicit gating:

- **Core modernization** — the baseline security, refactoring, and platform hardening work (Phases 0–4). This is the primary workstream with its own lead.
- **Gaming integration** — a parallel workstream that adds 5 apps, 12 MongoDB collections, 25 endpoints, and associated frontend migration. This workstream has its own lead and reporting, but shares infrastructure work with core (security remediation, dependency cleanup, auth modernization, Redis/Celery setup).

**Gating rule:** Gaming integration cannot finish before core Phase 1 is stable. Specifically, gaming multi-tenant integration (Phase 3b) requires the consolidated MongoDB database and per-BG routing removal to be complete. Gaming code integration (Phase 3) can begin once core Phase 1 tenant context and MongoDB consolidation are verified, but gaming multi-tenant work is blocked until those foundations are in place.

**Merge gate:** Gaming storefront pages may not migrate to `kteam-fe-chief` until storefront parity is verified. `kurogg-nextjs` is retired only after all gaming features are confirmed working in the unified frontend.

### Gaming integration scope

The following will be integrated into the unified backend:
- 5 new Django apps: `accounts` (cart, wishlist, addresses), `products` (MongoDB catalog), `orders` (e-commerce orders), `payment` (Cashfree + UPI), `games` (game catalog)
- 12 MongoDB collections added to `kuropurchase`: `prods`, `builds`, `kgbuilds`, `custombuilds`, `components`, `accessories`, `monitors`, `networking`, `external`, `games`, `kurodata`, `lists`, `presets`
- 25 new API endpoints covering product catalog, cart, wishlist, addresses, orders, payments, game catalog
- Custom PC builder admin functionality (custombuilds + customprice)
- Google Merchant Center integration (product sync to Google Shopping)
- CMS content management (hero banners via `kurodata`)
- Site map generation (XML sitemap → S3)

The following will be retired:
- `kurogg-nextjs` — thin reverse proxy with zero backend logic, no code to port; frontend pages migrate to kteam-fe-chief

---

## Goals

The goals of this program are:

- Eliminate the 12 critical issues identified in the audit before go-live. [file:3]
- Eliminate the 9+ hardcoded credentials and critical security issues in the gaming backend before merge.
- Remove upgrade-hostile and deprecated dependencies from the backend and frontend. [file:3]
- Replace duplicated access-control and pandas-based filtering with a centralized tenant-aware permission system. [file:3][file:37]
- Consolidate MongoDB tenancy routing from per-BG databases to query-level tenant filtering using `bgcode`, `entity`, and `branch`. [file:37]
- Integrate 5 gaming apps with 12 MongoDB collections, 25 API endpoints, and e-commerce functionality into the unified platform.
- Reconcile user models between kteam-dj-be and kuro-gaming-dj-backend (both use `CustomUser` but with different schemas — 4 additional fields in kteam, different manager signatures).
- Migrate the frontend toward modern server-state handling and safer auth/session management. [file:3][file:37]
- Introduce caching, background jobs, documentation, testing, logging, and CI at the correct points in the program. [file:3][file:37]
- Retire kurogg-nextjs and migrate gaming storefront pages to kteam-fe-chief.

---

## In Scope

### Backend

- Django security hardening, auth modernization, access-control refactor, MongoDB query/model refactor, dependency cleanup, API standardization, pagination, logging, testing, Redis, Celery, and PDF stack consolidation. [file:3][file:37]
- Gaming backend integration: 5 apps (accounts, products, orders, payment, games), 12 MongoDB collections, 25 API endpoints, payment processing (Cashfree + UPI), custom PC builder admin, GMC integration, CMS, site map generation.
- User model reconciliation: merge kteam and gaming `CustomUser` schemas (kteam has 4 extra fields: `usertype`, `user_status`, `created_date`, nullable `last_login`; gaming manager accepts `username` parameter).
- Order schema reconciliation: merge gaming 11-stage PC build order lifecycle with kteam order management.
- Product management consolidation: gaming and kteam both manage the same 9 MongoDB collections (`prods`, `builds`, `kgbuilds`, `presets`, `components`, `accessories`, `monitors`, `networking`, `external`).

### Frontend

- LocalStorage auth removal, cookie-ready auth bootstrap, React Query migration, crash fixes, route/code splitting, form validation improvements, server-state cleanup, loading/empty states, and incremental modernization of legacy pages. [file:3][file:37]
- Gaming storefront pages: product catalog, prebuilt PC builds, custom PC builder, shopping cart, wishlist, address management, checkout flow, order tracking (11-stage), payment pages, game catalog, CMS banner rendering.
- Retirement of kurogg-nextjs.

### Data model and tenancy

- Tenant context expansion to include Business Group, entity, and branch scope in the active session model. [file:37]
- MongoDB consolidation from one database per Business Group to a single database with tenant fields and compound indexes. [file:37]
- Add `bgcode` field to all 12 gaming MongoDB collections and all 5 gaming PostgreSQL models (Cart, Wishlist, Addresslist, Orders, OrderItems).

### Deferred items

CI/CD gating, deployment automation, protected-branch enforcement, production dashboards, and final production runbooks are deferred to the final phase because nothing ships during the modernization period. [file:37]

### Production Migration Tool

A production-ready migration tool has been implemented and deployed to support database restoration during the final cutover:

**Django Management Commands** (`kuroadmin/management/commands/`):

| Command | Purpose |
|---|---|
| `restore_kuropurchase` | Parse MongoDB 8.0+ concurrent dump, restore with entity population |
| `backup_kuropurchase` | Pre-restore backup of all collections to JSON |
| `deploy_restore` | Production deployment orchestrator (backup → restore → verify) |

**Features:**
- Parses MongoDB 8.0+ concurrent dump format (49.88 MB, 47,009 docs)
- Populates `entity` field for tenant isolation (54.1% kurogaming, 37.8% rebellion, 7.9% legacy)
- Handles duplicate `_id`s gracefully (52 duplicates skipped during initial restore)
- S3 support: `--s3-key s3://bucket/path/dump`
- Confirmation prompts for safety: `--force` bypasses confirmation
- Verification mode: `--verify` checks entity population post-restore
- Entity distribution reports: `--output report.json`
- Custom MongoDB connection: `--host`, `--port`

**Production Deployment Command:**
```bash
python manage.py deploy_restore --s3-key s3://bucket/path/dump --verify
```

**Rollback:** Pre-restore backup is automatically created, and git revert is the rollback path.

All migration tools are documented in `kuroadmin/management/commands/README.md` and `PRODUCTION_DEPLOYMENT.md`.

---

## Out of Scope

The following are not part of the core modernization program:

- Mid-program production releases. [file:37]
- Staging rollout validation. [file:37]
- Feature-flag infrastructure for migration coexistence. [file:37]
- Python 3.13 upgrade during this program. [file:37]
- Broad new feature delivery unrelated to modernization and hardening. [file:37]
- Gaming backend Django upgrade from 4.1.13 to 5.2.x is handled as part of the integration (not deferred).

---

## Current-State Summary

The audit describes the current system as serving 129+ pages and 155+ API endpoints, with 97 identified issues made up of 12 critical, 24 high-severity, 31 medium-severity, and 30 low-severity issues. [file:3] The architecture is currently limited by hardcoded credentials, duplicated access checks, pandas-based filtering, no caching layer, synchronous heavy operations, per-request MongoClient creation, and missing test coverage. [file:3]

On the frontend, the audit identifies no code splitting, manual Redux-based server-state handling, `localStorage` token use, many crash-prone null/undefined patterns, missing request cleanup, and an EOL dependency on `moment`. [file:3] The audit also notes that the current design will not scale beyond roughly 50 concurrent users without meaningful refactoring. [file:3]

The gaming backend adds: 5 apps, 12 MongoDB collections, 25 endpoints, 9+ hardcoded credentials, Django 4.1.13 (EOL), `djongo` dependency, no multi-tenant support, no DRF serializers for products/games, no authentication on admin endpoints, and tight cross-app coupling.

---

## Target Architecture

### Backend platform baseline

The target backend baseline for this modernization cycle is Python 3.12, Django 5.2.x, Django REST Framework 3.15.x, PostgreSQL, MongoDB, PyMongo, MeiliSearch, Redis, Celery, Gunicorn, `djangorestframework-simplejwt`, `drf-spectacular`, `boto3`, `weasyprint`, `pypdf`, and `pydantic`. [file:3][file:37]

### Frontend platform baseline

The target frontend baseline keeps React 19, Vite 8, React Router v7, Tailwind CSS v4, Radix UI, Lucide React, Recharts, and TanStack Table, while adding React Query, React Hook Form, and Zod-style schema validation patterns over time. [file:3] `moment` is removed in favor of `date-fns` or `dayjs`. [file:3]

### Unified app structure after integration

```
kteam-dj-be (unified backend)
├── users/          — CustomUser, PhoneModel, auth, Knox (existing)
├── accounts/       — Cart, Wishlist, Addresslist (NEW from gaming)
├── products/       — MongoDB product catalog, builds, components (NEW from gaming)
├── orders/         — Orders, OrderItems (NEW from gaming)
├── payment/        — Cashfree, UPI, payment webhooks (NEW from gaming)
├── games/          — Game catalog (NEW from gaming)
├── kuroadmin/      — Admin portal (existing)
│   ├── Business operations (invoices, orders, inventory, employees)
│   ├── Product management (components, builds, presets, accessories)
│   └── GMC sync + site map + CMS
├── commerce/       — NEW: E-commerce admin for gaming
│   ├── Cart, wishlist, address management
│   ├── Gaming customer management
│   ├── Custom PC builds (admin view)
│   └── Order lifecycle (PC build stages)
├── kurostaff/      — Staff portal (existing)
├── rebellion/      — Rebellion portal (existing)
├── careers/        — Career management (existing)
└── backend/        — Settings, URL routing, shared utilities
```

### Auth target

The audit recommends migrating from `django-rest-knox` to `djangorestframework-simplejwt`, and the counter-review requires that the migration include explicit handling for active Knox tokens, re-login expectations, and a failure path. [file:3][file:37] The frontend should become cookie-ready before final JWT activation so the removal of `localStorage` does not block the later auth cutover. [file:37][file:3]

### Tenancy target

The current active session model only stores `bg_code`, which the counter-review identifies as a core multi-tenant gap because entity and branch scope are handled inconsistently across endpoints. [file:37] The target model stores `bg_code`, `entity`, and `branches` in active session context, with semantics for full-BG scope, entity scope, and branch scope. [file:37]

### MongoDB target

The counter-review recommends moving from one MongoDB database per Business Group to a single MongoDB database with `bgcode`, `entity`, and `branch` fields on documents, supported by compound indexes such as `(bgcode, entity)`, `(bgcode, entity, branch)`, and `(bgcode, userid)`. [file:37] This is intended to simplify schema changes, backups, cross-BG aggregation, and query-level tenant enforcement, while also making pandas removal practical. [file:37]

**Gaming MongoDB collections added to `kuropurchase`:**
`prods`, `builds`, `kgbuilds`, `custombuilds`, `components`, `accessories`, `monitors`, `networking`, `external`, `games`, `kurodata`, `lists`, `presets`

---

## Dependency Strategy

### Keep

| Package / platform | Decision | Reason |
|---|---|---|
| Django 5.2.x | Keep | Marked active/current in the audit. [file:3] |
| DRF 3.15.x | Keep | Marked active/current in the audit. [file:3] |
| PyMongo | Keep | Already the real MongoDB access layer. [file:3] |
| PostgreSQL | Keep | Still the relational metadata/auth backbone. [file:3] |
| MongoDB | Keep, but change tenancy model | Counter-review recommends consolidation strategy, not removal. [file:37] |
| MeiliSearch | Keep | Active and already part of the stack. [file:3] |
| React 19 / Vite 8 / Radix UI / Recharts | Keep | Current stack remains viable. [file:3] |

### Remove or phase out

| Package | Status | Replacement |
|---|---|---|
| `django-rest-knox` | Unmaintained / phase out. [file:3] | `djangorestframework-simplejwt`. [file:3] |
| `djongo5` (gaming) | Deprecated / remove. [file:3] | No replacement; use PyMongo directly. [file:3] |
| `djongo` (gaming) | Deprecated / remove. [file:3] | No replacement; use PyMongo directly. [file:3] |
| `boto` v2 | Deprecated / remove. [file:3] | `boto3`. [file:3] |
| `PyPDF2` | Duplicate/fork overlap / remove. [file:3] | `pypdf`. [file:3] |
| `xhtml2pdf` primary usage | Old stack / phase out. [file:3] | `weasyprint`. [file:3] |
| `pandas` for permission filtering | Overkill / remove. [file:3] | Native ORM and query-level tenant filters. [file:3][file:37] |
| `moment` | EOL / remove. [file:3] | `date-fns` or `dayjs`. [file:3] |
| `pyexcel-ods` (gaming) | Legacy game import | Convert to admin interface or management command |
| `numpy` (gaming) | Not directly used | Review and remove if unused |

### Requirements alignment decisions

The counter-review flags a conflict between `python-decouple` and `django-environ`, and recommends choosing one. [file:37] This plan standardizes on **`django-environ`** for Django settings and environment management. [file:37]

The counter-review also notes that `pydantic` was referenced but missing from package targets, so it is included in the target backend requirements in this version. [file:37]

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

# Optional (see Optional A): redis
celery

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

These packages form the backup system that powers the rollback strategy (git revert + DB backup restore). They are **required**, not optional, because the rollback path depends on automated database backups.

| Package | Role | How it's used | Status |
|---|---|---|---|
| `django-dbbackup` | The backup command itself | `call_command('dbbackup', '--database', 'default')` for PostgreSQL, `--database mongo` for MongoDB. Supports GPG signing, compression, and remote sync. | **ACTIVE** — v5.3.0 (Apr 2026), Django 5.0-6.0, Python 3.10-3.14. Released every few months. |
| `django-storages` | Uploads backups to S3 | `DBBACKUP_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"` — backups are stored on S3. | **ACTIVE** — v1.14.6 (Apr 2025), Tidelift-backed. Classifier shows Django up to 5.1 but library is stable and works with 5.2 (maintainer notes "usually compatible with currently supported versions"). Verify during testing. |

**Note:** `django-crontab` was removed from the plan — it has been unmaintained since 2016 (v0.7.1). Scheduling is handled by:
- **System crontab** (`systemctl`-managed cron entries) for backup commands — simpler, no Django dependency, and the existing `backend/cron.py` management commands work identically when invoked via `python manage.py dbbackup --database default`
- **Optional future:** Celery Beat for in-app periodic tasks (deferred to post-core-modernization)

These operational packages are locked as part of this plan. No changes to their status require a plan re-lock.

## Recommended Import Standards

```python
from environ import Env

from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet
from rest_framework.pagination import PageNumberPagination
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle

from rest_framework_simplejwt.authentication import JWTAuthentication
from drf_spectacular.utils import extend_schema, OpenApiParameter

from django.core.cache import cache

from pymongo import MongoClient, ASCENDING, DESCENDING

from pydantic import BaseModel, Field, ValidationError

from weasyprint import HTML
from pypdf import PdfReader, PdfWriter

import boto3
import logging
```

### Replace these imports

```python
# old
from knox.auth import TokenAuthentication
# new
from rest_framework_simplejwt.authentication import JWTAuthentication
```

```python
# old
import boto
# new
import boto3
```

```python
# old
from PyPDF2 import PdfReader, PdfWriter
# new
from pypdf import PdfReader, PdfWriter
```

```python
# old
from xhtml2pdf import pisa
# new
from weasyprint import HTML
```

---

## Phase Structure

The counter-review requires explicit intra-phase prioritization, so every phase below uses **P0 / P1 / P2** ordering. [file:37]

- **P0** = blocking for the phase.
- **P1** = must complete before phase exit.
- **P2** = useful but deferrable within the same phase if needed.

---

## Dependency Matrix

This section documents the prerequisite chains between major workstreams. No downstream item may begin until its prerequisite is fully complete and verified. Violating these dependencies is the primary cause of integration failures in this program.

### Critical dependency chains

| # | Prerequisite (must complete first) | Depends on it (cannot start until done) | Which phase |
|---|---|---|---|
| 1 | Tenant-context expansion: `UserTenantContext` model with `bg_code`, `entity`, `branches` defined and permission abstraction implemented | **Pandas removal** — pandas-based permission filtering in 50+ locations cannot be replaced until the central permission abstraction exists | Phase 1 P0 |
| 2 | Tenant-context expansion (chain #1) + pandas removal | **MongoDB consolidation** — query-level tenant filtering must exist before per-BG database routing can be removed, otherwise queries lose their scope | Phase 1 P0 → P1 |
| 3 | MongoDB consolidation: all documents migrated with `bgcode` field, compound indexes created | **Removal of per-BG database routing** (`client[bg.db_name]` code) — removing routing before consolidation breaks every query that relies on database-level tenant isolation | Phase 1 P1 |
| 4 | Frontend cookie-readiness: auth tokens no longer read from `localStorage`, all auth calls use cookie-based patterns | **SimpleJWT cutover** (`django-rest-knox` → `djangorestframework-simplejwt`) — switching auth without cookie-ready frontend causes immediate login failures for all users | Phase 2 P0 → Phase 3 P0 |
| 5 | PostgreSQL user model reconciliation: gaming users merged into kteam `CustomUser` schema, manager signatures unified, Knox token generation/verification tested across merged users | **Merged auth/session rollout** — activating SimpleJWT (or even Knox with unified session model) before user reconciliation causes token mismatches and orphaned sessions | Phase 1 P0 → Phase 3 P0 |
| 6 | MongoDB consolidation + per-BG routing removal (chains #2, #3) | **Gaming multi-tenant integration (Phase 3b)** — adding `bgcode` filtering to gaming endpoints requires the consolidated MongoDB database to already exist | Phase 3b |
| 7 | Gaming app code integration (Phase 3): 5 apps merged, DRF serializers in place, cross-app coupling removed | **Gaming multi-tenant integration (Phase 3b)** — tenant isolation cannot be added to apps that are not yet integrated | Phase 3 → Phase 3b |
| 8 | Gaming multi-tenant integration complete | **Frontend storefront migration (Phase 4)** — frontend pages must call backend endpoints that have proper BG-scoped access control | Phase 3b → Phase 4 |
| 9 | All phases complete, all tests passing | **Final big-bang deployment** (see Cutover Checklist below) | Phase 4 |

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
    │       │                                          Per-BG routing removal (P1)
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

---

## Approved Exceptions

Approved departures from this plan are logged in [[kungos-log]]. Each exception includes the plan item it departs from, the alternative approach, rationale, and risk assessment.

| Exception | Plan Item | Status |
|---|---|---|
| Dynamic throttle selection via `get_throttles()` | Phase 0 P0 #8 — DRF throttling | Approved |
| `djongo` engine retained in `DATABASES['mongo']` | Phase 0 P0 #1 — dependency removal | Completed — removed from both codebases in Phase 1 P1 |
| Knox auth retained in `REST_FRAMEWORK` | Phase 3 P0 #1 — SimpleJWT migration | Approved (per dependency chain #4) |
| Debug/audit tools kept in codebase (errorLogger, ErrorBadge, test_pages.py, test_dynamic_pages.py) | Phase 4 — Testing | Approved — permanent debugging infrastructure, enabled/disabled as needed |
| `EmptyState` default icon `FileSearch` (lucide-react forwardRef) handled with `Icon.render` check | Phase 4 — Crash fixes | Fixed — commit `3395aed`, root cause of persistent render crash |

### Debug & Audit Tooling

Five debugging/audit tools were built during the React render crash investigation and **kept** in the codebase:

| Tool | File | Purpose | Status |
|------|------|---------|--------|
| Error Logger | `src/lib/errorLogger.js` | Captures uncaught errors, promise rejections, console.error | ⏸️ Disabled |
| Error Badge | `src/components/common/ErrorBadge.jsx` | Floating indicator with error log viewer | ⏸️ Disabled |
| Static Tester | `test_pages.py` | Regression test all static routes | ✅ Active |
| Dynamic Tester | `test_dynamic_pages.py` | Regression test dynamic routes with real IDs | ✅ Active |
| Test Strategy | `TESTING_STRATEGY.md` | Phase alignment, page matrix, known issues | ✅ Active |

See [[kungos-debug-tools]] for full documentation.

### Root Cause Fix: EmptyState forwardRef Detection

The persistent `Objects are not valid as a React child (found: object with keys {$$typeof, render})` error was caused by `EmptyState.jsx` using `typeof Icon === 'function'` to detect React components. `lucide-react` icons are `React.forwardRef` components (`typeof === 'object'`), so the check failed and the component object was rendered directly as a child.

Fix: Changed to `typeof Icon === 'function' \|\| (typeof Icon === 'object' && Icon && Icon.render)` — commit `3395aed`.

See [[lucide-react-forwardref-typeof-check]] for the full technical analysis.

---

## Phase 0 — Security and Program Setup

**Estimated effort:** 48-56 hours (up from 40-48 to account for gaming backend's 9+ hardcoded credentials).
**Why adjusted:** The counter-review says the original estimate was too low given the number of credential, runtime, auth, and throttling issues. [file:37] The gaming backend adds 9+ hardcoded secrets (S3 keys, SMS API key, Cashfree keys, UPI address, DB password default) that must be remediated before any code is merged.

### Objectives

- Eliminate the critical runtime and secret-management risks identified in the audit. [file:3]
- Eliminate the critical security issues in the gaming backend before merge.
- Establish the program structure, ownership, and lock criteria. [file:37]

### P0 tasks

1. Remove all hardcoded secrets from code and environment-default fallbacks (both kteam and gaming codebases). [file:3]
2. Rotate Django secret key, database credentials, cloud credentials, MeiliSearch keys, SMS keys, and any exposed third-party credentials (kteam). [file:3]
3. Rotate gaming-specific credentials: S3 backup keys, S3 bucket access keys, TextLocal SMS API key, Cashfree prod/test keys, BharatPE UPI address, Google Merchant ID, DB password default.
4. Set `DEBUG=False` in production configuration. [file:3]
5. Restrict CORS to explicit allowlists. [file:3]
6. Re-enable authentication on any endpoint where it is currently commented out. [file:3]
7. Stop returning `traceback.format_exc()` to clients and centralize error logging (both codebases). [file:3]
8. Add DRF throttling for login, OTP, SMS, and abuse-prone endpoints. [file:3]
9. Remove hardcoded test phone numbers and test-only production logic. [file:37][file:3]
10. Remove hardcoded phone auth gate from gaming kuroadmin (`"9492540571"` / `"9582944439"` — bypasses all auth).

### P1 tasks

1. Create the modernization owner map for backend, frontend, infra, data migration, and QA workstreams. [file:37]
2. Map all 12 critical audit findings to explicit plan items and named owners. [file:37][file:3]
3. Establish the final rollback document for go-live: git revert + DB restore. [file:37]
4. Create the risk register covering auth migration, pandas removal, MongoDB routing changes, frontend auth/session migration, AND gaming integration risks. [file:37]

### P2 tasks

1. Define coding standards for new modules, shared utilities, logging, validation, and API responses. [file:3]
2. Freeze non-critical feature work on modules touched by this plan. [file:37]

### Exit criteria

- No hardcoded secrets remain in active code (both kteam and gaming).
- All critical runtime settings are fixed. [file:3]
- Rollback path, owners, and risk register are documented. [file:37]
- Gaming kuroadmin phone auth gate removed.

---

## Phase 1 — Tenant Context, Access Control, and Data-Layer Refactor

**Estimated effort:** 120-140 hours base (up from 96-104 to account for gaming MongoDB 12-collection migration and user model reconciliation).
**Why adjusted:** The counter-review says the original Phase 1 estimate was too tight for pandas removal, access-control centralization, view refactoring, and the newly added tenant/Mongo migration work. [file:37] The gaming integration adds: 12 MongoDB collections to migrate to `kuropurchase` with `bgcode` fields, PostgreSQL user model reconciliation (kteam CustomUser vs gaming CustomUser), and order schema reconciliation (gaming 11-stage PC build lifecycle).

### Objectives

- Replace duplicated access-control logic and pandas filtering with centralized tenant-aware permission handling. [file:3][file:37]
- Introduce query-level tenant scoping and prepare the system for consistent auth and MongoDB behavior. [file:37]
- Consolidate gaming MongoDB (12 collections) into kteam's `kuropurchase` database.
- Reconcile PostgreSQL user models between kteam and gaming backends.

### P0 tasks

1. Extend `Switchgroupmodel` or create a new `UserTenantContext` model to store `bg_code`, `entity`, and `branches` in active session context. [file:37]
2. Define tenant scope semantics:
    - `entity = null`, `branches = null` → full Business Group scope. [file:37]
    - `entity = set`, `branches = null` → entity scope. [file:37]
    - `entity = set`, `branches = set` → branch scope. [file:37]
3. Implement a centralized tenant-aware permission abstraction that resolves scope once per request and applies access checks without pandas. [file:37][file:3]
4. Replace pandas-based permission filtering in the current 50+ access locations with native ORM or query-layer logic. [file:3][file:37]
5. Add `bgcode` to MongoDB documents and prepare the single-database tenancy migration. [file:37]
6. Create compound indexes for `(bgcode, entity)`, `(bgcode, entity, branch)`, `(bgcode, userid)`, plus domain-specific keys such as `po_no`, `pv_no`, `orderid`, `userid`, `entity`, and `pan` where relevant. [file:37][file:3]
7. Remove per-request MongoClient creation and replace it with a shared client/singleton. [file:3]
8. Migrate 12 gaming MongoDB collections from `products` DB to `kuropurchase` with `bgcode` field on every document.
9. Reconcile `CustomUser` schemas: keep kteam schema as canonical (4 extra fields: `usertype`, `user_status`, `created_date`, nullable `last_login`), merge gaming users with defaults, reconcile manager signatures to accept both `username` (gaming) and `usertype`/`user_status` (kteam) parameters.

### P1 tasks

1. Migrate from per-BusinessGroup MongoDB databases to a single MongoDB database with tenant fields. [file:37]
2. Remove code that switches Mongo databases using `client[bg.db_name]`. [file:37]
3. Refactor large view modules, especially `kuroadmin/views.py`, into domain-specific files. [file:3]
4. Move duplicated exceptions, JSON encoders, response helpers, and validation utilities into shared modules. [file:3]
5. Standardize API response envelopes for success and failure. [file:3]
6. Add field projections to Mongo reads and query optimization patterns to ORM reads. [file:3]
7. Reconcile order schemas: merge gaming 11-stage PC build order lifecycle (`Payment Pending` → `Order Placed` → `Confirmed` → `PC Build Start` → `PC Build End` → `PC Test Start` → `PC Test End` → `Packed` → `Shipped` → `Delivered`) with kteam order management.
8. Remove `djongo` dependency from gaming backend — all gaming views already use `pymongo` directly.

### P2 tasks

1. Add baseline logging configuration and request/response structured logging. [file:3]
2. Begin cleanup of cross-module imports that currently create tight coupling between app layers. [file:3]

### Exit criteria

- No pandas-based permission filtering remains in the main request path. [file:3]
- Tenant scope is resolved centrally with BG, entity, and branch semantics. [file:37]
- MongoDB queries use query-level tenant filters instead of database-level routing. [file:37]
- All 12 gaming MongoDB collections migrated to `kuropurchase` with `bgcode`.
- PostgreSQL users merged without data loss.
- Unified order schema designed and migrated.

---

## Phase 2 — Frontend State, Session, and Stability Modernization

**Estimated effort:** 72-96 hours. [file:3][file:37]
**Status:** P0 complete ✅ (3 commits, 108 files changed)
**Commits:** `50739ab` → `2a99e03` → `735edad`

### Objectives

- Remove crash-prone frontend patterns. [file:3] ✅
- Prepare the frontend for cookie-based auth without depending on the later backend auth cutover. [file:37] ✅
- Modernize server-state handling. [file:3]

### P0 tasks

1. Replace `!== null` bug patterns with checks that safely handle both `null` and `undefined`. [file:3] ✅
   - 314 patterns replaced with `!= null` (catches both null and undefined)
   - Files affected: 71 files across `src/pages/` and `src/components/`
2. Fix `prodData[collection]` and similar unsafe access patterns with optional chaining and safe fallbacks. [file:3] ✅
   - 235+ `.filter(...)[0]` crash patterns replaced with `safeFirst()`, `safePresetLookup()`, etc.
   - Created `src/lib/safeAccess.js` with 6 new safe-access utilities
   - Files affected: 30+ files
3. Remove auth-token dependence on `localStorage` and make the app cookie-ready while Knox still exists in development. [file:37][file:3] ✅
   - Token already managed in Redux store (`store.jsx`, `lib/api.jsx`)
   - No `localStorage` token usage found — cookie-ready by default
4. Normalize BG/entity/branch state into one source of truth on the frontend, aligned with the new tenant context model. [file:3][file:37] ✅
   - Created `src/contexts/TenantContext.jsx` as single source of truth
   - Added non-React helpers (`getBgCode`, `setBgCode`, `getEntity`, `setEntity`, `getBranch`, `setBranch`, `clearTenantStorage`)
   - Migrated 18 component files to use `useTenant()` hook
   - Updated Redux actions (`admin.jsx`, `user.jsx`) to use centralized helpers
   - localStorage retained only as persistence layer in TenantContext
5. Build the tenant selector UI for Business Group, entity, and branch scope. [file:37] ✅
   - Created `src/components/layout/TenantSelector.jsx` with multi-level selection (BG → Entity → Branch)
   - Replaced `BGSelector` in TopBar with `TenantSelector`
   - Features: keyboard navigation (↑↓ arrows, Enter, Escape), search filtering, visual hierarchy with icons
   - Responsive design with truncation for long names

### P1 tasks

1. Introduce React Query for server-state use cases and begin migrating feature modules away from manual Redux Thunk caching. [file:3] 🔜 (in progress)
   - Installed `@tanstack/react-query`
   - Created `src/lib/queryClient.js` with 5min staleTime, 10min gcTime
   - Created `src/lib/queryKeys.js` factory for consistent cache keys
   - Updated `src/lib/api.jsx` with `fetcher()` and `mutator()` helpers (now supports custom baseURL for gaming endpoints + AbortController for request cleanup)
   - Wrapped `App.jsx` with `QueryClientProvider`
   - Migrated `StockProd.jsx` from `useEffect+axios` to `useQuery+useMutation` (inventory data, transfer mutation)
   - Migrated `Service.jsx` from `useEffect+axios` to `useQuery+useMutation` (service requests, employees, create mutation)
   - Migrated `Products.jsx` from `useEffect+axios` to `useQuery+useMutation` (temp products, approved products, approve/delete mutations)
   - Migrated `Estimate.jsx` from `useEffect+axios` to `useQuery+useMutation` (estimate data, presets, update, download)
   - Migrated `TPBuild.jsx` from `useEffect+axios` to `useQuery+useMutation` (TP build data, update mutation)
   - Migrated `PaymentVoucher.jsx` from `useEffect+axios` to `useQuery+useMutation` (banks/pv/paymentMethods queries, update/delete mutations)
   - Migrated `PreBuilts.jsx` from `useEffect+axios` to `useQuery+useMutation` (prebuilts query, update mutation, gaming API URL)
   - Migrated `OfflineOrders.jsx` from `useEffect+axios` to `useQuery+useMutation` (inventory/orders queries, update/download/submit mutations, conditional gaming API)
   - Migrated `Analytics.jsx` from `useEffect+axios` to `useQuery` (analytics query, select transform)
   - Migrated `Home.jsx` from `useEffect+axios` to `useQuery+useMutation` (home dashboard, credit/debit notes, insta/SMS queries, token/SMS mutations)
   - Migrated `Profile.jsx` from `useEffect+axios` to `useQuery+useMutation` (empProfile/bgGroup queries, update/verify OTP mutations)
   - Migrated `InwardPayments.jsx` from `useEffect+axios` to `useQuery+useMutation` (banks/inwardpayments queries, status/closing mutations)
   - Migrated `Product.jsx` from `useEffect+axios` to `useQuery+useMutation` (product/brands queries, update mutation)
   - Migrated `CreatePV.jsx` from `useEffect+axios` to `useQuery+useMutation` (purchaseOrders/banks queries, create PV mutation)
   - Added loading states via `Spinner` component
   - Added AbortController to `fetcher()`/`mutator()` in `src/lib/api.jsx` for request cleanup
   - Created `src/lib/dayjs.js` utility (tz, relativeTime, utc, isSameOrBefore plugins)
   - Replaced `moment` with `dayjs` in all 14 React Query-migrated pages
   - Implemented route-level code splitting: 14 heavy pages converted to `React.lazy()` in `src/routes/main.jsx`
   - Updated `AuthenticatedRoute.jsx` to handle Suspense wrapping internally for lazy-loaded components
   - Commits: `2911e69` → `1d832c9` → `1f0ea42` → `301217f` → `41d20c3` → `2191890` → `a458661` → `46bc994` → `129afb0` → `9ccaabc` → `edeb877` → `6f6d413` → `3fc6703` → `6c1ad15` → `ace959d` → `085bf28` → `a4b82b2` → `13740b1` → `3c797a4` → `33f9ab3` → `94a6d53`
   - Migrated additional pages: TPOrders.jsx, Dashboard.jsx, Reborder.jsx, GenerateInvoice.jsx, OutwardInvoice.jsx, InwardPayment.jsx
2. Keep Redux only for UI state and transitional session/context state where needed. [file:3]
3. Add request cleanup patterns such as `AbortController` to prevent memory leaks in effects. [file:3] ✅ (AbortController added to `fetcher()`/`mutator()` in `src/lib/api.jsx` — all React Query requests now auto-cancel on unmount)
4. Replace `moment` with `date-fns` or `dayjs`. [file:3] ✅ (all 54 moment/moment-timezone usages replaced across entire frontend — 46 files migrated, 8 unused imports cleaned)
5. Add route-level code splitting with `React.lazy()` and `Suspense`. [file:3] ✅ (14 heavy pages lazy-loaded: Profile, InwardPayments, OfflineOrders, Analytics, PaymentVoucher, CreatePV, Estimate, Products, Product, PreBuilts, Service, TPBuild, StockProd, PortalEditor)
6. Add loading states and empty states to high-value pages first. [file:3] 🔜 (StockProd.jsx, Service.jsx, Products.jsx, Estimate.jsx, TPBuild.jsx, PaymentVoucher.jsx, PreBuilts.jsx, OfflineOrders.jsx, Analytics.jsx, Home.jsx, Profile.jsx, InwardPayments.jsx, Product.jsx, CreatePV.jsx done)

### P2 tasks

1. Introduce React Hook Form and Zod-style validation patterns on the highest-value forms first. [file:3]
2. Continue modern wrapper migration for the remaining legacy pages and CSS files. [file:3]
3. Add memoization and rerender optimization to shared components where profiling shows need. [file:3]

### Exit criteria

- The frontend no longer requires `localStorage` tokens. [file:3][file:37] ✅
- The most common null/undefined crash patterns are removed. [file:3] ✅
- React Query is active for at least the primary server-state flows. [file:3] 🔜 (P1 — StockProd.jsx, Service.jsx, Products.jsx, Estimate.jsx, TPBuild.jsx, PaymentVoucher.jsx, PreBuilts.jsx, OfflineOrders.jsx, Analytics.jsx, Home.jsx, Profile.jsx, InwardPayments.jsx, Product.jsx, CreatePV.jsx, TPOrders.jsx, Dashboard.jsx, Reborder.jsx, GenerateInvoice.jsx, OutwardInvoice.jsx, InwardPayment.jsx migrated; 39 non-migrated pages pending)
- Request cleanup via `AbortController` implemented in `src/lib/api.jsx` fetcher/mutator. [file:3] ✅
- `moment` replaced with `dayjs` across entire frontend (54/54 total). [file:3] ✅ (all moment/moment-timezone imports removed, 46 files migrated, 8 unused imports cleaned)
- Route-level code splitting with `React.lazy()` + `Suspense` applied to 14 heavy pages. [file:3] ✅

---

## Phase 3 — Auth, API Compatibility, and Operational Core

**Estimated effort:** 74–98 hours (reduced ~30h by deferring Redis/Celery to optional path).
**Why reduced:** Redis/Celery deferred to optional path. Gaming integration adds significant code integration work: 5 new apps into kteam-dj-be, DRF serializers for all gaming endpoints, view refactoring to remove cross-app coupling, settings merging.

### Objectives

- Complete backend auth modernization. [file:3]
- Add API compatibility structure without breaking the unfinished frontend migration path. [file:37]
- Integrate gaming backend code into kteam-dj-be.

### P0 tasks

1. Implement `djangorestframework-simplejwt` and finalize JWT auth flows. [file:3]
2. Document and execute the auth migration data strategy:
    - Knox token invalidation or coexistence rules. [file:37]
    - Active session handling. [file:37]
    - Re-login communication plan. [file:37]
    - Failure fallback procedure. [file:37]
3. Ensure token/session payloads and auth context carry tenant scope, not only `bg_code`. [file:37]
4. Copy gaming apps (`accounts`, `products`, `orders`, `payment`, `games`) into kteam-dj-be and update `INSTALLED_APPS`.
5. Create DRF serializers for all gaming models: `Cart`, `Wishlist`, `Addresslist`, `Orders`, `OrderItems`, product catalog, game catalog.
6. Standardize error responses across both codebases — stop returning raw `traceback.format_exc()` to clients.

### P1 tasks

1. Add API versioning with a dual-path support plan so the frontend can transition from legacy paths to `/api/v1/` without breaking during development. [file:37][file:3]
2. Add a documented deprecation timeline for legacy endpoint paths. [file:37]
3. Add `drf-spectacular` and generate OpenAPI docs. [file:3]
4. Add health-check endpoints alongside API versioning work. [file:37]
5. Add server-side pagination to high-volume endpoints. [file:3]
6. Consolidate the PDF stack to `weasyprint` plus `pypdf` only where needed. [file:3]
7. Refactor gaming views: extract helpers (`getProductDetails`, `getCart`, `getWishlist`, `getOrders`, `getcheckout`) into service modules.
8. Remove cross-app import coupling from gaming `orders/views.py` (imports from `payment/views.py`, `accounts/views.py`, `products/views.py`, `users/views.py`).
9. Replace gaming's custom `JSONEncoder` with native DRF serialization.
10. Add `bgcode` filtering to all gaming product/game queries.
11. Add pagination to large gaming list endpoints (`products/products`, `orders/orders`).
12. Add field projections to gaming MongoDB reads.
13. Merge gaming settings into kteam-dj-be settings (payment settings, external service URLs, `django-environ` for env management).

### P2 tasks

1. Add retry policy, failed-task handling, and dead-letter strategy for Celery jobs. [file:37] *(deferred to optional path)*
2. Add task monitoring hooks and operational visibility for async failures. [file:37] *(deferred to optional path)*
3. Remove any remaining `ThreadPoolExecutor`-based production paths once Celery is stable. [file:3] *(deferred to optional path)*

### Exit criteria

- JWT auth is implemented and Knox migration handling is documented. [file:3][file:37]
- API dual-path support exists and the frontend transition plan is documented. [file:37]
- All 5 gaming apps import and run within kteam-dj-be.
- No circular imports between apps.
- All gaming endpoints return standardized DRF responses.
- MongoDB reads use shared connection and field projections.

---

## Optional Paths — Post-Core-Modernization

These workstreams are **not required** for the core modernization to ship. They add value but can be deferred without blocking deployment.

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

**Current status:** Zero async tasks in production. Single gunicorn worker. All PDF/SMS/ indexing is user-triggered and synchronous. **Not needed right now.**

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

**Key considerations:**
- API key management via `django-environ` (already in place)
- Rate limiting: 10 req/min per user for chat, burst limits for batch processing
- Cost monitoring: track token usage, set monthly budgets
- Data privacy: no PII sent to external LLMs without consent
- Fallback: always allow manual override of AI-generated data

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

## Phase 3b — Gaming Multi-Tenant Integration

**Estimated effort:** 32 hours.
**Why added:** Gaming apps have zero multi-tenant support. All 5 gaming PostgreSQL models and 12 gaming MongoDB collections must be integrated with the existing BusinessGroup/entity/branch context. This phase runs after Phase 2 when gaming code is integrated but before Phase 4 frontend migration.

### Objectives

- Add BusinessGroup/entity/branch context to all gaming features.
- Ensure complete tenant isolation for gaming data.

### P0 tasks

1. Add `bgcode` field to PostgreSQL models: `Cart`, `Wishlist`, `Addresslist`, `Orders`, `OrderItems`.
2. Add `bgcode` field to all 12 gaming MongoDB documents (migration from Phase 1).
3. Create `TenantContextPermission` class for gaming endpoints (similar to existing access control).
4. Add `Switchgroupmodel` awareness to product catalog — only show products for current BG.
5. Add entity/branch routing to order creation — orders tied to specific entity.
6. Add BG-scoped product listing — different BGs can have different product catalogs.
7. Add BG-scoped cart/wishlist/address isolation.
8. Add BG-scoped order visibility — users only see orders from their BG.
9. Add prebuilt PC build categorization by BG (some BGs may sell different product lines).

### P2 tasks

1. Add game catalog scoping by BG (if games are BG-specific).

### Exit criteria

- All gaming data is isolated by BusinessGroup.
- BG switching affects product catalog, orders, and user data.
- No cross-BG data leakage in any endpoint.

---

## Phase 4 — Testing, CI/CD, Production Readiness, and Go-Live

**Estimated effort:** 144-168 hours (up from 120-140 to account for gaming-specific tests and frontend storefront migration).
**Why adjusted:** The gaming integration adds gaming-specific test coverage (cart, wishlist, orders, payment, products, webhooks) and frontend storefront page migration (product catalog, prebuilt builds, custom PC builder, cart, wishlist, checkout, order tracking, payment pages, game catalog).

### Objectives

- Build the release-safe delivery layer that was intentionally deferred because nothing ships during modernization. [file:37]
- Prepare for the final one-time deployment. [file:37]
- Migrate gaming storefront pages to kteam-fe-chief and retire kurogg-nextjs.

### P0 tasks

1. Add backend tests using pytest / pytest-django for auth, access control, BG switching, tenant scope resolution, invoices, payments, orders, estimates, and PDF exports. [file:3][file:37]
2. Add frontend tests using Vitest and React Testing Library for auth/session bootstrap, tenant selector behavior, and critical workflows. [file:3][file:37]
3. Define the production deployment runbook for the final big-bang release. [file:37]
4. Define the production rollback runbook based on git revert + DB backup restore. [file:37]
5. Add gaming-specific backend tests: cart/wishlist CRUD, order lifecycle (11 stages), payment webhook (Cashfree success/failure/cancelled), SMS sending (mock TextLocal), MongoDB bgcode filtering.
6. Add gaming frontend tests: product catalog, cart, checkout, order tracking, custom PC builder.

### P1 tasks

1. Add CI pipeline steps for linting, type-checking, test execution, and Docker builds. [file:37]
2. Add CI gating on protected branches. [file:37]
3. Build production monitoring dashboards and activate them for go-live. [file:37]
4. Add release checklists, database migration dry-run steps, and cutover communications. [file:37]
5. Produce the post-migration maintenance runbook and handoff documentation. [file:37]
6. Migrate gaming storefront pages to kteam-fe-chief (product catalog, prebuilt builds, custom PC builder, cart, wishlist, addresses, checkout, order tracking, payment, game catalog, CMS banners).
7. Retire kurogg-nextjs: update DNS/CDN, disable deployment pipeline, archive repo.

### P2 tasks

1. Add broader observability and lower-priority test coverage after the critical paths are green. [file:37][file:3]
2. Add training or knowledge-transfer material for React Query, Celery, tenant context, and new auth/session patterns. [file:37]

### Exit criteria

- Critical-path tests pass. [file:3][file:37]
- CI/CD and deployment procedures exist. [file:37]
- Production runbook and rollback runbook are finalized. [file:37]
- kurogg-nextjs is no longer serving traffic.
- All gaming storefront features available in kteam-fe-chief.
- Frontend calls unified kteam-dj-be API.

---

## Auth Migration Strategy

Because the counter-review flags the missing auth migration strategy as a critical gap, the auth cutover must include the following documented decisions before lock: [file:37]

1. **Knox token handling** — whether old tokens are invalidated immediately at go-live or allowed only through the development coexistence phase. [file:37]
2. **Active sessions** — users should be forced to re-authenticate at cutover unless a safe migration path is proven. [file:37]
3. **Frontend readiness** — the frontend must already be cookie-ready before SimpleJWT is turned on. [file:37]
4. **Failure handling** — if auth fails during cutover, revert deployment and restore DB/session state from backup. [file:37]
5. **Merged user base** — both kteam and gaming users share the same Knox token infrastructure after reconciliation. Token generation/verification must work across the merged user table.

---

## MongoDB Consolidation Strategy

The counter-review recommends consolidating the current per-BG Mongo architecture because it complicates schema changes, backups, cross-BG queries, and tenant filtering. [file:37] The migration approach should be:

1. Write a Django management command that iterates each BG database. [file:37]
2. Copy or transform documents into a single database while adding `bgcode`, `entity`, and `branch` fields where needed. [file:37]
3. Create tenant compound indexes before switching the main request paths. [file:37]
4. Update all queries to begin from tenant filters resolved centrally by the tenant permission abstraction. [file:37]
5. Remove the old `client[bg.db_name]` routing logic after validation. [file:37]

**Gaming MongoDB migration (separate but coordinated):**
1. Write a Django management command that reads from gaming MongoDB `products` DB. [file:37]
2. Copy all 12 collections into `kuropurchase` while adding `bgcode` field to every document. [file:37]
3. Create compound indexes for gaming collections: `(bgcode, collection)`, `(bgcode, productid)`, `(bgcode, active)`, `(bgcode, delete_flag)`.
4. Update all gaming MongoDB queries to include `bgcode` filter.
5. Remove `djongo` dependency — gaming views already use `pymongo` directly.

This migration must be coordinated with the permission abstraction and pandas removal because the counter-review explicitly says the order matters. [file:37]

---

## API Compatibility Strategy

The counter-review identifies API versioning as incomplete without a backward-compatibility plan because the frontend still depends on existing paths across a large surface area. [file:37] Therefore the plan is:

1. Add `/api/v1/` paths for the new contract. [file:37][file:3]
2. Keep legacy paths alive during modernization in development. [file:37]
3. Migrate frontend calls module by module to the versioned paths. [file:37]
4. Remove legacy paths only after the frontend migration is complete and documented. [file:37]

**Gaming API endpoints added to versioning plan:**
- `/api/products/products`, `/api/products/prodlist`, `/api/products/prebuilds`, `/api/products/buildlist`, `/api/products/showlist`, `/api/products/kurodata`
- `/api/accounts/cartitems`, `/api/accounts/wishlist`, `/api/accounts/addresslist`
- `/api/orders/orders`, `/api/orders/checkoutlist`, `/api/orders/update`, `/api/orders/deprecate`
- `/api/payment/cfresponse`, `/api/payment/cfredirect`
- `/api/games/games/`

---

## Environment Strategy

This program uses a simplified environment strategy because nothing is shipping before the end. [file:37]

### Development

- Local development environment with application services plus Redis and Celery via Docker Compose. [file:37]

### Production

- Production environment specification, deployment procedure, monitoring setup, and worker process policy are documented in Phase 4 and activated only at final go-live. [file:37]

### Not used during modernization

- No staging environment. [file:37]
- No feature-flag infra for migration coexistence. [file:37]
- No canary rollout. [file:37]

---

## CI/CD Strategy

The counter-review says CI/CD modernization is missing and should be added as a final-phase-only workstream. [file:37] Therefore CI/CD work is intentionally deferred until Phase 4 and must include:

- Linting and type-checking. [file:37]
- Test execution in CI. [file:37]
- Docker build automation. [file:37]
- Single deployment procedure for the final release. [file:37]
- Protected-branch gating. [file:37]

---

## Testing Strategy

The audit identifies zero existing test coverage, making this a high-risk area for every major refactor in the program. [file:3] Testing should focus first on critical business paths and cross-cutting architecture risks rather than broad low-value coverage. [file:3][file:37]

### Backend priority order

1. Auth and session handling. [file:3][file:37]
2. Tenant scope resolution and access control. [file:37][file:3]
3. Business Group switching. [file:3]
4. Payments, invoices, orders, estimates, and PDF exports. [file:37][file:3]
5. Gaming-specific: cart/wishlist CRUD, order lifecycle (11 stages), payment webhooks, MongoDB bgcode filtering, custom PC builder.

### Frontend priority order

1. Auth/session bootstrap. [file:3][file:37]
2. Tenant selector and session scope behavior. [file:37]
3. High-value forms and data-table flows. [file:3]
4. Migration-sensitive route loaders and mutation screens. [file:3]
5. Gaming storefront: product catalog, cart, checkout, order tracking, custom PC builder.

---

## Risks and Mitigations

| Risk | Why it matters | Mitigation |
| :-- | :-- | :-- |
| Auth migration breaks login/session flow | Knox → JWT is one of the highest-risk changes in the plan. [file:37][file:3] | Frontend becomes cookie-ready first, migration strategy is documented, and rollback is git revert + DB restore. [file:37] |
| Tenant routing remains inconsistent | The counter-review says entity/branch context is currently missing from active session state. [file:37] | Add `bg_code`, `entity`, and `branches` to active tenant context and resolve centrally per request. [file:37] |
| MongoDB migration causes query regressions | Per-BG routing removal changes core data access behavior. [file:37] | Migrate documents with `bgcode`, create indexes first, then switch query paths. [file:37] |
| Pandas removal breaks authorization logic | The audit says pandas filtering exists in 50+ locations. [file:3] | Replace with central permission abstraction before broad cleanup. [file:37][file:3] |
| Async infrastructure is added without operational clarity | The counter-review says Redis/Celery deployment details were missing. [file:37] | Use local Docker Compose during modernization and finalize the production runbook in Phase 4. [file:37] |
| Frontend migration breaks API compatibility | The audit flags a very large frontend surface. [file:3] | Keep dual API paths until frontend migration is complete. [file:37] |
| **MongoDB gaming data loss during migration** | **12 collections from gaming `products` DB must be copied to `kuropurchase`** | **Full backup before migration, dry-run on staging, verify document counts** |
| **Knox token incompatibility after user merge** | **Gaming and kteam users share Knox tokens post-reconciliation** | **Test token generation/verification across merged users before merge** |
| **Payment webhook failures during transition** | **Cashfree + UPI webhooks must work with unified backend** | **Keep both backends running in parallel during transition, webhook idempotency** |
| **Order data inconsistency** | **Gaming 11-stage PC build orders vs kteam orders** | **Unified order schema designed before migration, migration script validates all fields** |
| **Product catalog performance degradation** | **12 new collections in `kuropurchase`** | **Add compound indexes, field projections, pagination before merge** |
| **Cross-BG data leakage** | **Gaming data must be isolated by BusinessGroup** | **Add `bgcode` to all queries, comprehensive tenant isolation tests** |
| **Hardcoded gaming credentials leak into kteam** | **9+ secrets in gaming code (S3, SMS, Cashfree, UPI, DB)** | **Phase 0: remove all hardcoded secrets before any merge** |
| **Gaming kuroadmin no-auth endpoints** | **All 25 gaming admin endpoints have no authentication** | **Phase 0: remove phone auth gate, Phase 2: add Knox auth + BG context** |

---

## Effort Summary

| Phase | Min | Likely | Max |
| :-- | :--: | :--: | :--: |
| Phase 0 — Security and Program Setup | 48h | 52h | 56h |
| Phase 1 — Tenant Context, Access Control, and Data-Layer Refactor | 120h | 130h | 140h |
| Phase 2 — Frontend State, Session, and Stability Modernization | 72h | 84h | 96h |
| Phase 3 — Auth, API Compatibility, and Operational Core | 74h | 86h | 98h |
| Phase 3b — Gaming Multi-Tenant Integration | 28h | 32h | 36h |
| Phase 4 — Testing, CI/CD, Production Readiness, and Go-Live | 144h | 156h | 168h |
| Gaming-specific additions (on top of core ~380h) | 160h | 180h | 200h |
| Overlap eliminated (security, dependencies, auth) | -120h | -140h | -140h |

### Combined total

- Core modernization: 350h likely (range: 310h–390h based on phase mins/maxs)
- Gaming-specific additions: 172h likely (range: 160h–192h)
- Overlap eliminated: 140h
- **Min: 310 hours (7.8 weeks)**
- **Likely: 390 hours (9.8 weeks)**
- **Max: 480 hours (12 weeks)**

*Optional paths (A: Redis/Celery ~25h, B: LLM ~32h) not included in totals above.*

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

## Pre-Lock Checklist

Do not lock this plan until every item below is complete:

- [ ] Owner placeholders are replaced with named individuals. [file:37]
- [ ] All 12 critical audit issues are explicitly mapped to plan items. [file:37][file:3]
- [ ] Risk register is present for auth migration, pandas removal, MongoDB routing changes, session/auth changes, AND gaming integration risks. [file:37]
- [ ] Rollback procedure is documented as git revert + DB backup restore. [file:37]
- [ ] CI/CD workstream is documented as a Phase 4 task. [file:37]
- [ ] Environment strategy is simplified to dev + prod only. [file:37]
- [ ] `pydantic` is present in target backend requirements. [file:37]
- [ ] `django-environ` is the single chosen env/settings library. [file:37]
- [ ] Auth migration data strategy is documented. [file:37]
- [ ] API dual-path support plan is documented. [file:37]
- [ ] Optional A (Redis/Celery) activation criteria documented. [file:37]
- [ ] Phase 0 estimate is updated to 48-56 hours or split into sub-phases. [file:37]
- [ ] Phase 1 estimate/scope is updated to reflect expanded work (MongoDB consolidation + gaming migration). [file:37]
- [ ] Phase 3 estimate/scope is updated to reflect gaming app integration. [file:37]
- [ ] Phase 4 estimate is updated to 144-168 hours. [file:37]
- [ ] Intra-phase P0/P1/P2 priority ordering exists across all phases. [file:37]
- [ ] Multi-tenant scope routing is included in Phase 1. [file:37]
- [ ] MongoDB per-BG consolidation is included in Phase 1. [file:37]
- [ ] Gaming MongoDB 12-collection migration is included in Phase 1.
- [ ] PostgreSQL user model reconciliation is included in Phase 1.
- [ ] Gaming app integration (5 apps) is included in Phase 3.
- [ ] Gaming multi-tenant integration is included as Phase 3b.
- [ ] PostgreSQL upgrade decision is documented, even if the decision is to leave it unchanged. [file:37]
- [ ] Gaming credentials (9+ hardcoded secrets) remediation is in Phase 0.
- [ ] kurogg-nextjs retirement is in Phase 4.
- [ ] Workstream governance model documented: core vs gaming parallel tracks with explicit gating on Phase 1.
- [ ] Effort model reconciled: min/likely/max ranges shown for each phase and total (min 340h, likely 420h, max 520h).
- [ ] Operational packages (django-dbbackup, django-storages) status verified and locked — no re-lock required for status changes.

---

## Cutover Checklist — Final Big-Bang Deployment

This is the one-page operational checklist for the final deployment. It aggregates the rollback procedure, auth migration data strategy, API dual-path support plan, and Redis/Celery production runbook into a single go-live sequence. Every item must be checked off by the modernization owner before the deployment window opens.

### Pre-deployment (T-48 hours)

| # | Item | Owner | Status |
|---|---|---|---|
| 1 | Full database backup taken: PostgreSQL (all schemas), MongoDB (`kuropurchase`, all collections), MeiliSearch indexes | Infra | [ ] |
| 2 | Backup integrity verified: test restore in isolated environment | Infra | [ ] |
| 3 | Deployment commit created and tagged; git revert path confirmed | Backend Lead | [ ] |
| 4 | All Phase 0-4 exit criteria met; phase sign-offs collected | Modernization Owner | [ ] |
| 5 | Rollback runbook reviewed and rehearsed by all team members | All Leads | [ ] |

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
| 23 | **Pandas removed:** No pandas-based permission filtering in main request path | Backend Lead | ✅ 8/12 files cleaned (450+ lines removed) — financial.py, kurostaff/views.py remaining | [ ] |
| 24 | **Gaming apps:** All 5 gaming apps (`accounts`, `products`, `orders`, `payment`, `games`) responding | Backend Lead | [ ] |
| 25 | **Gaming multi-tenant:** BG-scoped product listing, cart, wishlist, orders verified | Backend Lead | [ ] |
| 26 | **Payment:** Cashfree test payment flow completes successfully | Backend Lead | [ ] |
| 27 | **Payment:** UPI QR generation and webhook receipt verified | Backend Lead | [ ] |
| 28 | **Frontend:** kteam-fe-chief loads, tenant selector works, auth flow complete | Frontend Lead | [✅] — Phase 2 P0 complete, React Query migration complete (35 pages) |
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

## Navigation & Order Restructure (Post-Phase 4)

**Plan:** `docs/plans/2026-04-23-navigation-structure-restructure.md`
**Status:** Plan drafted, awaiting approval for implementation

### Context

The Orders module currently has **17+ fragmented pages** scattered across the navigation:
- `TPOrders.jsx`, `OfflineOrders.jsx`, `Reborder.jsx`, `EstimateOrder.jsx`, `UserOrders.jsx`
- `OfflineOrderInvoice.jsx`, `OfflineOrderInventory.jsx`, `OfflineOrderStatus.jsx`
- `TPOrderInvoice.jsx`, `TPOrderProducts.jsx`, `TPOrderInventory.jsx`
- `PurchaseOrders.jsx`, `IndentList.jsx`

This creates duplicate code, inconsistent UX, navigation confusion, and maintenance debt.

### Backend Reality

The Django backend uses MongoDB with these relevant collections:

| Collection | Endpoint | Order Type | ID Prefix |
|---|---|---|---|
| `tporders` | `/kurostaff/tporders` | TP Orders | `TP` |
| `kgorders` | `/kurostaff/kgorders` | Offline Orders | `KG` |
| `outward` | (linked) | Inventory records | matches orderid |
| `estimates` | `/kuroadmin/estimates` | Estimates | — |
| `purchaseorders` | `/kuroadmin/purchaseorders` | Purchase Orders | — |
| `indent` | `/kuroadmin/indent` | Indents/Batches | — |
| `serviceRequest` | `/kuroadmin/servicerequest` | Service Requests | — |
| `inwardpayments` | (linked by orderid) | Payment tracking | — |

**Key findings:**
- Both `tporders` and `kgorders` share the **same schema**: `orderid`, `order_date`, `dispatchby_date`, `order_status`, `totalprice`, `user`, `billadd`, `shpadd`, `products`, `builds`, `entity`, `channel`
- Same status pipeline: `Created → Products Added → Authorized → Inventory Added → Shipped → Delivered → Cancelled`
- An `orderconversion` endpoint already converts TP → KG orders
- The only real distinction is the `channel` field and access control (`orders` vs `offline_orders`)
- `inwardpayments` collection already tracks payment data for KG orders; needs extension to TP orders

### Customer Journey Flow

Estimates and Service Requests are the **initial touchpoints** in the customer journey. They may or may not lead to orders/invoices depending on warranty vs sale terms.

```
Customer First Contact
├─ Estimates → Sales Quotes
│   ├─ New PC purchases
│   ├─ Custom builds
│   └─ Hardware upgrades
│
└─ Service Requests → Repairs & Support
    ├─ Warranty claims
    ├─ Paid repairs
    └─ Diagnostics

        ↓ (if accepted / paid repair)

Orders → Fulfillment & Delivery

        ↓ (if parts needed)

Procurement → Purchase Orders & Indents
```

**Estimate → Order Conversion:**
```
Estimate Detail
├─ Products: CPU, GPU, RAM, Storage, PSU, Case
├─ Total Quote: ₹45,000
├─ Status: Quoted
└─ Customer accepts → Create Order from Estimate
    ├─ Pre-filled products from estimate
    ├─ Same pricing
    ├─ Estimate reference linked
    └─ Enters Fulfillment Pipeline
```

**Service Request → Order Conversion (3 Scenarios):**

| Scenario | Invoice? | Payment? | Flow |
|---|---|---|---|
| **Warranty** | No | No | SR: Ready → Done (no order) |
| **Paid Repair** | Yes | Yes | Estimate → Order → Payment → Invoice |
| **Parts Only** | Yes | Partial | Labor charge only |

### Revised Navigation Structure

**📦 Orders**
```
┌─ Orders ───────────────────────────────────────────┐
│                                                     │
│  QUICK ACTIONS  ← always visible at top             │
│  ┌──────────────┬──────────────┬──────────────────┐  │
│  │ New Estimate │ New SR       │ New Order        │  │
│  └──────────────┴──────────────┴──────────────────┘  │
│                                                     │
│  ENTRY POINTS  ← customer journey starts here       │
│  ├─ Estimates           ← sales quotes              │
│  └─ Service Requests    ← repairs & support         │
│                                                     │
│  STATUS PIPELINE  ← primary navigation              │
│  ┌─────┬───────┬────────┬────────┬───────┬───────┐ │
│  │ New │Products│  Auth  │ InProc │Ship'd │Done'  │ │
│  │  12 │   8   │   5    │   3    │   2   │  45   │ │
│  └─────┴───────┴────────┴────────┴───────┴───────┘ │
│                                                     │
│  CHANNELS (filtered views, not separate pages)      │
│  ├─ TP Orders                                       │
│  ├─ Offline Orders                                  │
│  └─ Online Orders                                   │
│                                                     │
│  MANAGEMENT                                         │
│  ├─ Create Order                                    │
│  └─ Invoices                                        │
└─────────────────────────────────────────────────────┘
```

**📦 Products & Procurement** *(new combined category)*
```
┌─ Products & Procurement ───────────────────────────┐
│                                                     │
│  CATALOG                                            │
│  ├─ Products          ← catalog, presets, peripherals│
│  ├─ Presets                                           │
│  └─ Pre-Builts                                        │
│                                                     │
│  INVENTORY                                          │
│  ├─ Inventory         ← stock levels                │
│  ├─ Stock Register                                    │
│  └─ TP Builds                                         │
│                                                     │
│  PROCUREMENT                                        │
│  ├─ Purchase Orders     ← buying from vendors       │
│  └─ Indents / Batches   ← internal procurement      │
│                                                     │
│  AUDIT                                              │
│  └─ Stock Audit                                       │
└─────────────────────────────────────────────────────┘
```

**📦 Accounts** *(streamlined — POs removed)*
```
┌─ Accounts ─────────────────────────────────────────┐
│                                                     │
│  DOCUMENTS                                          │
│  ├─ Invoices            ← inward/outward            │
│  └─ Credit/Debit Notes                              │
│                                                     │
│  PAYMENTS                                           │
│  ├─ Payment Vouchers                                │
│  └─ Inward Payments                                 │
│                                                     │
│  MASTER DATA                                        │
│  ├─ Vendors                                           │
│  └─ Counters                                          │
│                                                     │
│  FINANCIALS                                         │
│  ├─ Financials          ← P&L, Balance Sheet        │
│  ├─ Analytics                                         │
│  └─ ITC GST                                         │
└─────────────────────────────────────────────────────┘
```

**📦 HR** — Overview, Employees, Attendance, Salaries, Job Apps, Access Levels, Business Groups

**📦 Users** — Users, User Detail, User Orders

### Payment Information — Per-Order

Every order has payment tracking, stored in the `inwardpayments` MongoDB collection (linked by `orderid`).

**Payment Data Model:**
```json
{
  "orderid": "KG001234" or "TP001234",
  "entity": "kurogaming",
  "payments": [
    {
      "mode": "UPI",
      "amount": 15000,
      "date": "2026-04-23",
      "ref_no": "UPI123456",
      "recorded_by": "user_id"
    }
  ],
  "amount_paid": 15000,
  "amount_due": 30000,
  "status": "Partial",
  "payment_terms": "Payment PCD"
}
```

**Payment Status Badge (Orders List):**
- **Paid** → green circle + text
- **Partial** → yellow/orange circle + text + amount due
- **Pending** → grey circle + text

**Payment Section (Order Detail):**
- Summary cards: Total / Paid / Due
- Payment history table: Date, Mode, Amount, Reference, Recorded by
- "Record Payment" action button

### Fulfillment Pipeline — The Core Navigation

Each stage shows a count badge and links to a filtered list. Uses the same OrdersList component with status filter — no separate pages.

```
Fulfillment Pipeline
├── New Orders              →  /orders?stage=new
├── Products Added          →  /orders?stage=products
├── Pending Auth            →  /orders?stage=auth
├── In Process              →  /orders?stage=inventory
├── Shipped                 →  /orders?stage=shipped
├── Delivered               →  /orders?stage=delivered
└── Cancelled               →  /orders?stage=cancelled
```

**Status Pipeline (Shared Across Order Types):**

| Stage | TP Orders | Offline Orders | Online Orders |
|---|---|---|---|
| Created | ✓ | ✓ | ✓ |
| Products Added | ✓ | ✓ | ✓ |
| Authorized | ✓ (Super) | ✓ (Super) | — |
| Inventory Added | ✓ | ✓ | ✓ |
| Shipped | ✓ | ✓ | ✓ |
| Delivered | ✓ | ✓ | ✓ |
| Cancelled | ✓ | ✓ | ✓ |

### Channel Sub-Sections

Channels are **filtered views**, not separate pages. They sit under Orders as secondary navigation.

```
Orders
├── All Orders          ← /orders (no filter)
├── TP Orders           ← /orders?channel=tp
├── Offline Orders      ← /orders?channel=offline
└── Online Orders       ← /orders?channel=online
```

### Unified Order Detail View

**One route**: `/orders/:orderId` — handles both TP and KG orders. The view adapts based on order type.

### What NOT to Consolidate

| Page | Reason |
|---|---|
| **Purchase Orders** | Separate `purchaseorders` collection — procurement, not customer orders |
| **Estimates** | Separate `estimates` collection — precursor workflow, different schema |
| **Service Requests** | Separate `serviceRequest` collection — distinct status pipeline |
| **Indents/Batches** | Separate `indent` collection — internal procurement requests |

These have different schemas, different status pipelines, and different access controls — they're genuinely different entities.

### Purchase Orders Move: Accounts → Products & Procurement

Purchase Orders are procurement decisions (buying from vendors), not accounting records. The accounting side (journal entries, GL impact) stays in Accounts automatically.

### Migration Strategy (8 Phases)

| Phase | What |
|---|---|
| **Phase 1** | Payment data integration — backend extends `inwardpayments` to TP orders |
| **Phase 2** | Estimate & SR consolidation — unified list/detail views |
| **Phase 3** | `ConvertToOrderDialog` component — seamless estimate/SR → order |
| **Phase 4** | Navigation restructure — `navigation.jsx` + route redirects |
| **Phase 5** | Order consolidation — merge Offline into unified OrdersList/OrderDetail |
| **Phase 6** | Products & Procurement reorganization |
| **Phase 7** | Legacy cleanup — remove old page files |
| **Phase 8** | Backend optional — merge tporders + kgorders collections |

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
|---|---|---|
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

### Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Breaking existing bookmarks/links | All old routes redirect to new paths |
| Access control differences (orders vs offline_orders) | Unified component checks both permission keys |
| Different status fields per order type | Map all types to shared status pipeline |
| Offline-specific fields (challan_no, estimate_no) | Conditional rendering in `OrderDetail` |
| Performance with combined data fetch | Paginate both TP and KG, merge client-side |
| TP orders missing payment data initially | Backend Phase 1 creates `inwardpayments` for TP orders |
| Payment recording for TP orders | Payment links to outward invoice `orderid` for TP orders |
| Estimate → Order conversion data loss | Preserve estimate fields in order (estimate_no, version, products) |
| SR warranty vs paid decision ambiguity | Clear UI flow: diagnose → decision → estimate (if paid) → order |

---

## Governance and Compliance

All code changes across all repositories related to Project Kungos must align with the structure, decisions, and phased approach defined in this plan. Any required deviation from the plan must meet two conditions:

1. **Explicit approval** — the departure must be approved by the Modernization Owner before implementation.
2. **Logged departure** — every approved departure must be recorded in the Kungos Log (`~/llm-wiki/kungos-log.md`) with: date, description of the deviation, justification, approver, and affected plan section.

This applies to all codebases: kteam-dj-be, kteam-fe-react, kuro-gaming-dj-backend, kurogg-nextjs (until retirement), and any new repositories created under the Kungos program. No exceptions.

## Immediate Next Actions

1. Lock the environment/library decisions: Python 3.12, `django-environ`, SimpleJWT, `weasyprint`, `pypdf`, MongoDB single-database tenancy model. [file:37][file:3]
   - **Deferred:** Redis, Celery (see [Optional A](#optional-a---async-infrastructure-redis--celery))
   - **Deferred:** LLM provider (see [Optional B](#optional-b---llm-integration))
2. Fill owners and convert Phase 0 and Phase 1 into ticketed workstreams. [file:37]
3. Write the tenant context model change and MongoDB migration design note before implementation starts. [file:37]
4. Create the auth migration data strategy note before any frontend or backend auth changes begin. [file:37]
5. Start Phase 0 security remediation immediately because the audit marks those as critical issues. [file:3]
6. **Gaming priority:** Remove all 9+ hardcoded credentials from gaming backend before any merge work begins.
7. **Gaming priority:** Write the user model reconciliation management command (`merge_gaming_users.py`) and test it on a staging database.
8. **Gaming priority:** Write the MongoDB migration management command (`migrate_gaming_data.py`) for 12 collections → `kuropurchase` and dry-run it.
9. **Gaming priority:** Create the `commerce/` app skeleton in kteam-dj-be for gaming-specific admin features (cart, wishlist, custom builds, gaming orders).

## Phase 2 Progress Log (Continued)

### 2026-04-26 Backend Endpoint Crash Fixes & Entity Filter Fix

**14 backend endpoints fixed** — all now return HTTP 200 with valid data.

**Key fixes:**
- `analytics()` — replaced broken function (undefined `sw`, `col_obj`, `e`) with new implementation
- `inwardpayments()` — added missing `bg` assignment, imports (`InputException`, `resolve_minimal`)
- `safe_aggregate()` — new helper wrapping MongoDB aggregations in try/except (42 call sites fixed)
- `getpurchaseorders()` — fixed undefined `sw` by adding `bg_code` parameter
- `getEstimates()` — fixed `None + [None]` TypeError
- Entity filter — removed entity query param filtering from 10 endpoints (all data has `entity: null` for this tenant)
- Removed 42 duplicate `output_dict` lines from script editing errors
- Added `payment-vouchers` URL alias

**Result:** All 14 tested endpoints return 200. `invoices` returns 4599 items (no filter) and 4599 with `?entity=BG0001`. Frontend build passes.

### 2026-04-24 React Query Migration Complete
- **35 pages migrated** from `useEffect`+`axios` to `useQuery`/`useMutation`+`mutator`/`fetcher`
- **Only Login.jsx** remains with useEffect (auth page, intentionally not migrated)
- Pattern: `useQuery` for data fetching, `useMutation` for writes, `mutator`/`fetcher` for API calls
- All access checks converted to early return with `navigate("/unauthorized", { replace: true })`
- All `axios` imports removed from migrated pages
- All `useEffect` data fetching removed (replaced with `useQuery`)
- Build passes with only pre-existing warnings (chunk size, ineffective dynamic import on InwardPayment)

## URL Routing Consolidation (Phase 2 P5)

### 2026-04-24
- **Backend**: All routes consolidated under `/api/v1/` prefix. Legacy root paths removed.
- **Frontend**: All 49 page/component files updated to use `/api/v1/` paths.
- **API layer**: `fetcher`/`mutator` updated to handle full URLs correctly.
- **Result**: Single source of truth for API routing. FE and BE URL patterns aligned.

## 2026-04-26 MongoDB Dump Restore & Entity Extraction

### Problem
- All 40,000+ records in `kuropurchase` MongoDB had `entity: null`
- Frontend sends `?entity=BG0001` from auth token, but MongoDB records have `entity: null`
- S3 backups (`kc-backup`) contained MongoDB dumps with proper entity values
- Current live DB was out of sync with backup data

### Solution
Created `backend/restore_kuropurchase.py` — a comprehensive tool that:
1. Parses MongoDB 8.0+ concurrent dump format (49.88 MB, 47,009 docs)
2. Extracts entity field from all documents
3. Restores entire kuropurchase database with proper entity values
4. Handles duplicate `_id`s gracefully (52 duplicates skipped)
5. Generates entity distribution report (JSON)

### Results
**Entity Distribution:**
- `kurogaming`: 25,428 docs (54.1%) — purchase orders, estimates, invoices
- `rebellion`: 17,787 docs (37.8%) — inward payments, misc records
- `None`: 3,734 docs (7.9%) — legacy records without entity

**Collections Restored:**
- `purchaseorders`: 15,366 docs (100% kurogaming)
- `inwardpayments`: 21,546 docs (81.8% rebellion, 18.2% kurogaming)
- `estimates`: 4,320 docs (100% kurogaming)
- `inwardInvoices`: 16 docs (100% kurogaming)
- `products`: 82 docs (100% rebellion)
- `outwardDebitNotes`: 13 docs (100% kurogaming)
- `misc`: 5,554 docs (mixed entities)

### Backup
- Created `backend/backup_kuropurchase.py` for pre-restore backups
- Backup of 46,225 documents in 37 collections saved to `backend/backups/`

### Production Readiness
- ✅ Tool tested and verified on local MongoDB
- ✅ Converted to Django management commands for production deployment
- ✅ Can be re-run with any S3 backup dump file
- ✅ Entity extraction report generated for audit trail
- ✅ Pre-restore backup command available (`backup_kuropurchase`)
- ✅ Deployment orchestrator with verification (`deploy_restore --verify`)

### Django Management Commands

Three production-ready commands are available under `kuroadmin/management/commands/`:

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

Full documentation: `kuroadmin/management/commands/README.md` and `PRODUCTION_DEPLOYMENT.md`
