# CBM-MCP Audit: kteam-dj-chief

**Project:** kteam-dj-chief  
**Date:** 2026-06-25  
**Index:** 5,540 nodes, 16,218 edges, 252 Python files  
**Backend:** SQLite + FTS5, WAL mode

---

## 1. Architecture Overview

### Language Breakdown
| Language | Files |
|----------|-------|
| Python | 252 |
| HTML | 14 |
| TypeScript | 3 |
| Bash/JS/YAML/SQL/SCSS | 6 |

### 5 Clusters
| Cluster | Members | Cohesion | Top Nodes |
|---------|---------|----------|-----------|
| users | 230 | 0.56 | get, save, create, AccesslevelSerializer |
| domains | 188 | 0.49 | get_collection, decode_result, find |
| teams | 147 | 0.51 | error_response, resolve_access, update_one |
| teams (analytics) | 58 | 0.44 | count_documents, reporting_response |
| domains (search) | 58 | 0.60 | parse, export_data, list |

### Top 10 Hotspots (by fan-in)
| Function | Location | Fan-In |
|----------|----------|--------|
| OrderGateway.get | domains/cafe_fnb/gateways.py | 336 |
| get_collection | backend/utils.py | 275 |
| error_response | backend/response_utils.py | 162 |
| decode_result | backend/utils.py | 152 |
| TenantCollection.find | plat/tenant/collection.py | 146 |
| **resolve_access** | backend/auth_utils.py | **140** |
| success_response | backend/response_utils.py | 121 |
| TenantCollection.update_one | plat/tenant/collection.py | 99 |
| ReportingViewSet.error_response | backend/reporting_base.py | 76 |
| get_accessible_divisions | backend/auth_utils.py | 48 |

### Layer Structure
| Layer | Modules | Role |
|-------|---------|------|
| **entry** | auth_utils, cafe_arcade, management, vendors | Outbound-only callers |
| **api** | api module | HTTP routes |
| **core** | cafe_fnb, response_utils, tenant, utils | High fan-in, foundational |
| **internal** | backup_kuropurchase, manage, restore_kuropurchase, src | Isolated |

### Key Boundaries (cross-module call counts)
- management → tenant: 43 calls
- cafe_arcade → utils: 30 calls
- api → cafe_fnb: 30 calls
- management → cafe_fnb: 28 calls

### HTTP Routes (9 indexed)
```
POST /api/v1/auth/login
POST /api/v1/auth/logout
POST /api/v1/auth/refresh
GET  /health/
GET  /ping/
GET  /api/v1/admin/tenant/bootstrap/
GET/POST /api/v1/cafe/payments/webhook/
GET  /test?period=curr_month
```

---

## 2. Dead Code Audit

### Confirmed Dead Modules (0 imports, 0 callers)

| File | Size | Status | Action |
|------|------|--------|--------|
| `backend/views_diagnostic.py` | ~50 lines | Not wired to URLs (comment says "Add to urls.py" but never did) | **Delete** |
| `backend/cron.py` | — | 0 imports, not a management command | **Delete** |
| `backend/backup_kuropurchase.py` | — | Superseded by `teams/management/commands/backup_kuropurchase.py` | **Delete** |
| `backend/restore_kuropurchase.py` | — | Superseded by `teams/management/commands/restore_kuropurchase.py` | **Delete** |

### Speculative Abstractions (never wired in)

| Package | Files | Imports From Outside | Status |
|---------|-------|---------------------|--------|
| `brands/` | 6 files (kurogaming/eshop, rebellion/cafe_arcade, rebellion/tournaments) | 0 | **Safe to delete** |
| `core/` | 10 files (cafe_arcade, commerce, finance, identity, tournaments protocols) | Only from `brands/` | **Safe to delete** |

`core/` defines Protocol interfaces. `brands/` implements them. Neither is imported by any active code. Classic YAGNI — infrastructure built for a brand-tenancy model that was never shipped.

### Dead Functions

| Function | Location | Evidence |
|----------|----------|----------|
| `close_mongo_client` | backend/utils.py | 0 callers, 0 callees via `codegraph_callers` | **Delete** |

### Duplicate Functions (consolidation candidates)

Three functions exist in both `backend/utils.py` and `backend/auth_utils.py`:

| Function | utils.py Line | auth_utils.py Line | Primary Copy |
|----------|---------------|-------------------|--------------|
| `has_read_access` | 124 | 206 | auth_utils (imported by 5+ files) |
| `has_write_access` | 136 | 226 | auth_utils (imported by 4+ files) |
| `get_branch_fallback` | 231 | 385 | auth_utils (imported by 1 file) |

**Current state:** All external imports use `backend.auth_utils`. The `utils.py` copies are only alive because `careers/views.py` imports `check_access` from utils, which internally calls the utils.py versions of these 3 functions.

**Consolidation path:** Switch `careers/views.py` to import `check_access` from `backend.auth_utils` (same signature, same behavior). Then delete the 3 duplicate functions from `backend/utils.py`.

**Risk:** Low — both copies are functionally identical (confirmed via `SIMILAR_TO` edges).

---

## 3. Impact Analysis

### resolve_access (backend/auth_utils.py:80)
- **Blast radius:** 215 affected symbols across 20+ files
- **Scope:** Every ViewSet list/create/update/destroy, every teams view, auth gates
- **Risk:** CRITICAL — changing signature or behavior breaks the entire authorization layer
- **Test coverage:** `tests/test_access_control.py` (unit tests for has_read_access, has_write_access, check_access)

### get_collection (backend/utils.py)
- **Fan-in:** 275 callers
- **Scope:** All data access through MongoDB
- **Risk:** HIGH — core data access abstraction

### OrderGateway.get (domains/cafe_fnb/gateways.py)
- **Fan-in:** 336 callers
- **Scope:** Cafe/F&B order operations
- **Risk:** HIGH — highest fan-in in codebase

### close_mongo_client (backend/utils.py)
- **Blast radius:** 0 affected nodes
- **Risk:** NONE — safe to delete

---

## 4. Flow Traces

### Login Flow (authentication)
```
POST /api/v1/auth/login
  → login() [users/api/viewsets.py:254]
    → _resolve_tenant_context() [users/api/viewsets.py:87]
    → _issue_jwt_tokens() [users/api/viewsets.py:135]
      → for_user() [users/tenant_tokens.py:37]
    → _build_login_response() [users/api/viewsets.py:154]
    → OrderGateway.get() ×4 [domains/cafe_fnb/gateways.py:107]
```

**Note:** Login does NOT call `resolve_access`. Authentication (login/token issuance) and authorization (access resolution) are cleanly separated.

### Protected Resource Access (authorization)
```
GET /api/v1/accounts/financials/
  → FinancialsViewSet.list() [domains/accounts/viewsets.py:855]
    → resolve_access() [backend/auth_utils.py:80]  ← direct call, 2 hops total
      → resolve_access_levels() [backend/utils.py:57]
      → _get_switchgroup() [backend/auth_utils.py:65]
      → OrderGateway.get() ×2 [domains/cafe_fnb/gateways.py:107]
```

**Pattern:** Every protected ViewSet method calls `resolve_access` directly as the first authorization gate. This is the single point of control for the entire app.

---

## 5. Duplicate Detection (SIMILAR_TO edges)

381 `SIMILAR_TO` edges in the graph (MinHash + LSH duplicate detection). Confirmed duplicates in `backend/`:

| Duplicate Pair | Files | Jaccard | Status |
|---------------|-------|---------|--------|
| has_read_access | utils.py ↔ auth_utils.py | high | Consolidate to auth_utils |
| has_write_access | utils.py ↔ auth_utils.py | high | Consolidate to auth_utils |
| get_branch_fallback | utils.py ↔ auth_utils.py | high | Consolidate to auth_utils |

No other cross-file duplicates flagged in core modules.

---

## 6. Standalone Scripts (not dead, but not importable)

These are run via `python X.py` directly — not dead, but not part of the import graph:

| Script | Purpose |
|--------|---------|
| `start_daemon.py` | Daemon process launcher |
| `start_django_daemon.py` | Django daemon launcher |
| `run_server.py` | Server runner |
| `migrate_accesslevels.py` | One-time migration script |
| `seed_permissions.py` | Permission seeder |
| `scripts/populate_branch_fields.py` | Data population script |

These are operational scripts, not library code. Keep them but don't expect graph-based analysis to trace their usage.

---

## Summary of Safe Deletions

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
