# Audit Verification: cbm-mcp-audit-kteam-dj-chief.md

| Field | Value |
|-------|-------|
| Project ID | `kteam-dj-chief` |
| Primary entity ID | `db12f8` |
| Entity type | `session` |
| Short description | Cross-index verification of CBM-MCP audit claims against target spec — actionable change plan |
| Status | `complete` |
| Source references | `/home/chief/llm-wiki/cbm-mcp-audit-kteam-dj-chief.md` (audit), `/home/chief/llm-wiki/Kung_OS/specs/` (target spec), `/home/chief/llm-wiki/Kung_OS/architecture/` (arch docs) |
| Generated | 25-06-2026 |
| Next action / owner | Execute Phase 1 (safe deletions), then Phase 2 (spec-aligned protocol placement) |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief`
**Reference docs:** `/home/chief/llm-wiki/cbm-mcp-audit-kteam-dj-chief.md` (source audit)
**Target spec:** `/home/chief/llm-wiki/Kung_OS/specs/domain_specs/` (identity, cafe, gaming, ecommerce)
**Architecture:** `/home/chief/llm-wiki/Kung_OS/architecture/` (multi_tenancy, rbac, identity_layer, platform_primitives)
**Key files for this task:** None created or modified — read-only verification

---

## Executive Summary

The audit (`cbm-mcp-audit-kteam-dj-chief.md`) was generated from the **CBM-MCP index** (5,540 nodes, 16,218 edges). Verified against **both CBM and codegraph indexes**. The actionable findings (dead code, duplicates, consolidation path) are accurate. The metrics and evidence contain significant errors.

**Two indexes, different coverage:**

| Metric | CBM-MCP | codegraph |
|--------|---------|-----------|
| Nodes | 5,540 | 3,602 |
| Edges | 16,218 | 8,870 |
| Files | 328 (incl. HTML templates) | 258 (code only) |
| SIMILAR_TO edges | 381 (MinHash+LSH) | 0 |
| Edge types | 19 (incl. SEMANTICALLY_RELATED, FILE_CHANGES_WITH) | 6 (calls, contains, imports, references, instantiates, extends) |
| HTML templates | 14 indexed | 0 |

CBM indexes Django templates and has structural analysis (SIMILAR_TO, SEMANTICALLY_RELATED, FILE_CHANGES_WITH). codegraph is code-only with simpler edge types. Both have the same `login()` → `OrderGateway.get()` false positive.

---

## Verified Claims

### ✅ ACCURATE — Dead Code (all 4 confirmed via both indexes + grep)

| File | Evidence | Verdict |
|------|----------|---------|
| `backend/views_diagnostic.py` | 0 imports in CBM, 0 in codegraph, 0 grep matches | **Safe to delete** |
| `backend/cron.py` | 0 imports in CBM, 0 in codegraph, 0 grep matches | **Safe to delete** |
| `backend/backup_kuropurchase.py` | 0 imports; superseded by `teams/management/commands/backup_kuropurchase.py` | **Safe to delete** |
| `backend/restore_kuropurchase.py` | 0 imports; superseded by `teams/management/commands/restore_kuropurchase.py` | **Safe to delete** |

### ✅ ACCURATE — Speculative Abstractions

| Package | Evidence | Verdict |
|---------|----------|---------|
| `brands/` (6 files) | 0 imports from outside `brands/` (grep confirmed) | **Safe to delete** |
| `core/` (10 files) | Only imported by `brands/`; 0 imports from active code (grep confirmed) | **Safe to delete** |

`brands/` implements Protocol interfaces defined in `core/`. Neither is imported by any active code.

**Spec alignment analysis:** The specs *do* require protocol interfaces (gaming_spec §7.2, cafe_spec §1.2). But they specify protocols live in **domain packages** (`gaming.protocols`, `cafe.protocols`), not a separate `core/` package. Brand-specific logic is handled via **Division tenant scope** (`div_code`), not separate code packages. The cafe_spec explicitly says: **"Rename `rebellion/cafe/` — Brand name on generic code is misleading"** (meaning the code IS generic, just misnamed under a brand).

**Verdict:** The *concept* (protocol-based architecture) is spec-aligned. The *structure* (`core/` + `brands/` packages) diverges from spec. Safe to delete — the protocol pattern will be implemented correctly when domains are built per spec.

### ✅ ACCURATE — Dead Function

| Function | Evidence | Verdict |
|----------|----------|---------|
| `close_mongo_client` (`backend/utils.py:37`) | 0 callers in codegraph, 0 grep matches beyond definition | **Safe to delete** |

### ✅ ACCURATE — Duplicate Functions (confirmed via CBM SIMILAR_TO + source)

| Function | utils.py | auth_utils.py | CBM Jaccard | Verdict |
|----------|----------|---------------|-------------|---------|
| `has_read_access` | :124 | :206 | 1.000 | Consolidate to auth_utils |
| `has_write_access` | :136 | :226 | 1.000 | Consolidate to auth_utils |
| `get_branch_fallback` | :231 | :385 | 1.000 | Consolidate to auth_utils |

**Consolidation path verified:** `careers/views.py:9` is the only file importing `check_access` from `backend.utils`. All other files (10+) import from `backend.auth_utils`. Switching `careers/views.py` to auth_utils makes the utils.py copies dead.

### ✅ ACCURATE — Language Breakdown (CBM only)

| Language | CBM Count | Verified |
|----------|-----------|----------|
| Python | 252 | ✅ grep matches |
| HTML | 14 | ✅ All in `templates/kuroadmin/` (Django templates codegraph skips) |
| TypeScript | 3 | ✅ |
| Bash | 2 | ✅ `start_django.sh`, `run_dev.sh` |
| JavaScript | 2 | ✅ |
| YAML | 1 | ✅ |
| SQL | 1 | ✅ `db_backup.sql` |
| SCSS | 1 | ✅ `assets/src/djetler.scss` |

### ✅ ACCURATE — SIMILAR_TO Edges (CBM only)

381 SIMILAR_TO edges confirmed in CBM (Jaccard range 0.953–1.000). The 3 cross-file duplicates in `backend/` are the only ones flagged in core modules.

### ✅ ACCURATE — Standalone Scripts

All 5 scripts confirmed present: `start_daemon.py`, `start_django_daemon.py`, `run_server.py`, `migrate_accesslevels.py`, `seed_permissions.py`.

### ✅ ACCURATE — HTTP Routes (CBM)

9 Route nodes in CBM, matching audit list exactly:

```
POST /api/v1/auth/login
POST /api/v1/auth/logout
POST /api/v1/auth/refresh
GET  /health/
GET  /ping/
GET  /api/v1/admin/tenant/bootstrap/
GET  /api/v1/cafe/payments/webhook/
POST /api/v1/cafe/payments/webhook/
GET  /test?period=curr_month
```

Note: codegraph indexes 297 route nodes (includes all Django URL patterns, not just entry points). CBM's 9 is the curated entry-point list.

---

## ❌ INACCURATE — Metrics & Evidence

### Fan-In Numbers Inflated

| Function | Audit Claims | CBM Direct CALLS | codegraph Impact | Verdict |
|----------|-------------|-------------------|-------------------|---------|
| `OrderGateway.get` | 336 | 10 | 247 (depth=1) | **Inflated 3-34×** |
| `get_collection` | 275 | — | 292 (depth=1) | Close (codegraph matches) |
| `resolve_access` | 140 | — | 142 (depth=1) | Accurate |
| `error_response` | 162 | — | — | Unverifiable — generic name |
| `decode_result` | 152 | — | — | Unverifiable — generic name |

**Root cause:** Audit "fan-in" counts are not direct CALLS (CBM: 10 for OrderGateway.get). They don't match codegraph impact either (247 vs 336). Likely from a different analysis method or index version. Ranking order is correct; absolute numbers are not trustworthy.

### Login Flow Trace — False Positive

Audit claims: `login()` → `OrderGateway.get() ×4`

**Both indexes show this link, but source code proves it wrong.** `login()` at `users/api/viewsets.py:254-332` calls only:
- `_resolve_tenant_context(user)` — line 330
- `_issue_jwt_tokens(user, tenant_context)` — line 331
- `_build_login_response(...)` — line 332

None of these call `OrderGateway.get()`. The graph trace resolves `KuroUser.objects.get()` (a Django ORM call) to `OrderGateway.get()` due to the generic name "get". **Same bug in both CBM and codegraph.**

**Corrected login flow:**
```
POST /api/v1/auth/login
  → login() [users/api/viewsets.py:254]
    → _resolve_tenant_context() [users/api/viewsets.py:87]
      → TenantCollection.distinct() [plat/tenant/collection.py:94]
    → _issue_jwt_tokens() [users/api/viewsets.py:135]
      → TenantAwareRefreshToken.for_user() [users/tenant_tokens.py:37]
    → _build_login_response() [users/api/api/viewsets.py:154]
      → UserSerializer, AccesslevelSerializer, build_permissions_object
```

Authentication and order lookup ARE cleanly separated — the audit's conclusion is correct, but the evidence (OrderGateway.get ×4) is a graph resolution error.

### Cluster Analysis — Not in Either Index

Audit claims 5 clusters with cohesion scores (0.44–0.60). **Neither CBM nor codegraph stores cluster/cohesion data.** No cluster properties on nodes, no cluster metadata. This was either computed by a separate tool not available for verification, or fabricated.

### Layer Structure — Not in Either Index

Audit claims 4 layers (entry/api/core/internal). **No layer metadata in either index.** Not verifiable.

---

## Summary of Safe Deletions (Confirmed)

| Item | Type | Risk | Lines Saved (est.) |
|------|------|------|-------------------|
| `backend/views_diagnostic.py` | Dead module | NONE | ~50 |
| `backend/cron.py` | Dead module | NONE | ~30 |
| `backend/backup_kuropurchase.py` | Superseded | NONE | ~80 |
| `backend/restore_kuropurchase.py` | Superseded | NONE | ~100 |
| `brands/` (entire package) | Speculative | NONE | ~150 |
| `core/` (entire package) | Speculative | NONE | ~100 |
| `close_mongo_client` | Dead function | NONE | ~10 |
| 3 duplicates in utils.py | After switching careers/views import | LOW | ~40 |

**Total estimated reduction:** ~560 lines, 0 functional impact.

**Consolidation prerequisite:** Switch `careers/views.py:9` from `from backend.utils import check_access` to `from backend.auth_utils import check_access` before deleting the 3 duplicate functions from `backend/utils.py`.

**Spec note:** The `core/` + `brands/` deletion is safe because the spec defines a different structure (protocols in domain packages, brand logic via tenant scope). The protocol *concept* is preserved; the *packages* are not.

---

## Target Spec vs Current State

### What the spec says (4 domain specs + architecture docs)

| Spec | Status | What It Defines |
|------|--------|-----------------|
| `identity_spec.md` | ~60% done | Unified identity, extension tables, phone lookup, auth linkage |
| `cafe_spec.md` | ~30% done | Separate cafe-fnb domain, OrderGateway, protocol chain, session-attached orders |
| `gaming_spec.md` | ~20% done | Tournament service, protocol enforcement, tenant-scoped queries |
| `ecommerce_spec.md` | ~10% done | E-commerce domain (eshop) |
| `multi_tenancy.md` | ~70% done | BG → Division → Branch hierarchy, cascade-code PKs, shared DB |
| `rbac_system.md` | ~50% done | Role-based access control |
| `identity_layer.md` | ~40% done | Identity layer design |
| `platform_primitives.md` | ~50% done | Platform primitives |

**Target architecture:** Django REST API, PostgreSQL + MongoDB, tenant-scoped via `bg_code`/`div_code`/`branch_code`, protocol interfaces per domain, outbox pattern for async, JWT auth.

### Key divergence: Protocol placement

| What exists | What spec says |
|-------------|----------------|
| `core/tournaments/protocols.py` (ITournamentsService) | `gaming/protocols.py` (IGamingTournamentService) |
| `core/commerce/protocols.py` (IOrderService, IWalletService) | `ecommerce/protocols.py` |
| `core/cafe_arcade/protocols.py` | `cafe/protocols.py` (ICafeFnbService) |
| `brands/kurogaming/eshop/services.py` — implements core protocols | Brand logic via `div_code` tenant scope, not code packages |
| `brands/rebellion/cafe_arcade/services.py` — implements core protocols | Generic cafe code in `cafe/` domain, not under brand name |

**The brands/core structure is a speculative plugin model that was never wired in.** Delete it. When domains are built, place protocols per spec.

## Changes Needed

### Phase 1: Safe Deletions (zero risk, ~560 lines)

| # | Action | Files | Prerequisite |
|---|--------|-------|-------------|
| 1 | Delete dead modules | `backend/views_diagnostic.py`, `backend/cron.py` | None |
| 2 | Delete superseded scripts | `backend/backup_kuropurchase.py`, `backend/restore_kuropurchase.py` | None (replaced by management commands) |
| 3 | Delete dead function | `close_mongo_client` in `backend/utils.py:37` | None |
| 4 | Fix import, delete duplicates | Switch `careers/views.py:9` to `from backend.auth_utils import check_access`, then delete 3 functions from `backend/utils.py` | Do import switch first |
| 5 | Delete speculative packages | `brands/` (entire), `core/` (entire) | None — 0 imports |

**Order:** 1-3 in any order. 4 must do import switch before deletion. 5 independent.

### Phase 2: Spec-Aligned Protocol Placement (future, when building domains)

When implementing domain specs, place protocols in domain packages per spec:

```
domains/
├── cafe/
│   ├── protocols.py   # ICafeFnbService (per cafe_spec §1.2)
│   ├── services.py
│   └── gateways.py
├── gaming/
│   ├── protocols.py   # IGamingTournamentService (per gaming_spec §7.2)
│   ├── services.py
│   └── gateways.py
└── ecommerce/
    ├── protocols.py   # IOrderService, IWalletService
    ├── services.py
    └── gateways.py
```

Brand-specific logic handled via `div_code` tenant scope — not separate code packages.

### Phase 3: Known Issues from Chief Review

Per `chief-review.md`:
- **H1:** Cafe `OrderGateway` bypasses protocol layer (tight coupling, God object) — fix when building cafe domain per spec
- **MongoDB naming skew** — collection names inconsistent with spec
- **Missing DLQ** for outbox failures — add when outbox is implemented

## Caveats & Uncertainty

1. **CBM vs codegraph discrepancy:** CBM indexes 328 files (incl. HTML templates, JSON backups); codegraph indexes 258 (code only). Use CBM for comprehensive analysis, codegraph for code-specific tracing.
2. **Generic name resolution bug:** Both indexes conflate `X.objects.get()` (Django ORM) with `OrderGateway.get()`. Any trace involving "get" needs manual source verification.
3. **Fan-in methodology unknown:** Audit's fan-in numbers don't match either index's direct or transitive counts. The ranking is useful; the absolute numbers are not.
4. **Cluster/cohesion unverifiable:** No cluster data in either index. May have been computed externally or hallucinated.
5. **Backup JSON files in index:** CBM indexes `backend/backups/*.json` as Module nodes — these are data files, not code. They inflate node counts.
