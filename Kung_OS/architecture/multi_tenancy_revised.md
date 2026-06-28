# Multi-Tenancy Architecture — Revised

**Status:** Constitution (stable, long-lived)
**Last updated:** 2026-06-28
**Predecessor:** `multi_tenancy.md` (2026-06-26)
**Authoritative references:** `CANONICAL_NAMING.md`, `endpoint_contract_spec.md` §5, `postgresql_schema.md` §4, `mongodb_schema.md` §2

---

## Canonical Glossary

| Term | Canonical Name | Legacy Name | Description |
|------|---------------|-------------|-------------|
| Business Group | `bg_code` | `bgcode` | Top-level tenant (e.g., `KURO0001`) |
| Division code | `div_code` | `division` | Single division identifier (e.g., `KURO0001_001`) |
| Branch code | `branch_code` | `branch` | Single branch identifier (e.g., `KURO0001_001_001`) |
| Division scope | `div_codes` | `division[]`, `entity` | Array of all accessible division codes (authorization scope) |
| Branch scope | `branch_codes` | `branches[]` | Array of all accessible branch codes (authorization scope) |
| Active division | `active_div_code` | `entity[0]` | Current active division (singular, from scope) |
| Active branch | `active_branch_code` | `branches[0]` | Current active branch (singular, from scope) |
| Identity | `identity_id` | `userid` | Stable person PK (replaces CustomUser PK) |

**Naming rule:** The canonical singular form (`div_code`, `branch_code`) refers to a single code. The plural/array form (`div_codes`, `branch_codes`) refers to the authorization scope array. Both are canonical — use the form that matches the context.

---

## JWT Claims Target

| Claim | Type | Source | Description |
|-------|------|--------|-------------|
| `bg_code` | string | active context | Business Group (required) |
| `div_codes` | array[string] | authorization scope | All accessible division codes |
| `branch_codes` | array[string] | authorization scope | All accessible branch codes |
| `active_div_code` | string | active context | Current active division |
| `active_branch_code` | string \| null | active context | Current active branch (nullable) |
| `identity_id` | string | `users_identity` | Stable person PK |
| `scope` | string | active context | Scope level: `'full'` \| `'division'` \| `'branch'` |

**Scope vs active context:** The JWT carries both authorization scope (`div_codes[]`, `branch_codes[]` — all accessible) and active context (`active_div_code`, `active_branch_code`, `scope` — current selection).

**Active-context convention:** `div_codes[0]` is always the active division. `branch_codes[0]` is always the active branch. The JWT claims `active_div_code` and `active_branch_code` are explicit aliases for `div_codes[0]` and `branch_codes[0]` — they MUST always be equal. Session variables and ContextVar reflect the **active context** (singular), not the full scope.

**Invariant:** `active_div_code == div_codes[0]` and `active_branch_code == branch_codes[0]` MUST hold at all times. If they diverge, the JWT is stale and must be regenerated.

**Authority statement:** The JWT is the **authoritative source of tenant context for every request**. All request-time tenant context resolution MUST read from the JWT. The DB (`UserTenantContext`) is the persistence layer — updated by switch endpoints, read by `resolve_access` as fallback. The ContextVar is the in-memory carrier — populated by middleware from JWT, consumed by application code.

---

## Principle

KungOS is a shared-database multi-tenant system. All data — PostgreSQL and MongoDB — is tenant-scoped. There are no separate databases per tenant.

### Core Rule

Every query, every write, every aggregation **MUST** include tenant scope (`bg_code`, optionally `div_code`, optionally `branch_code`). There are no exceptions.

### Authority Hierarchy

1. **JWT** (request-time) — authoritative for every request. Middleware extracts from JWT.
2. **ContextVar** (in-memory) — populated by middleware from JWT. Consumed by application code.
3. **UserTenantContext** (persistence) — updated by switch endpoints. Read by `resolve_access` as fallback.
4. **RLS** (database-level) — enforces isolation using session variables from ContextVar.

**No layer may override the JWT.** If the JWT says `bg_code = KURO0001`, all layers MUST use `KURO0001`.

### Exception Rule: Public and HMAC-Authenticated Endpoints

The JWT authority rule has two explicit exceptions:

| Endpoint Type | Auth Method | Tenant Resolution | Rationale |
|---------------|-------------|-------------------|-----------|
| **Public catalog endpoints** (e.g., `/cafe/games`, `/cafe/price-plans`, `/eshop/products`, `/tournaments/`) | None (no auth) | Tenant context is **not required** — these endpoints return BG-scoped data filtered by query params or are genuinely public (game catalogs, price plans) | No user context to resolve |
| **HMAC-authenticated webhooks** (e.g., `/eshop/payment/webhook`) | HMAC signature verification | Tenant context is resolved from the **payment/order record**, NOT from `request.auth` | Webhooks are not JWT-authenticated; tenant must be derived from the payload |

**Webhook tenant-resolution contract:**
1. Verify HMAC signature using shared secret
2. Extract tenant context from the payment/order record in the payload (e.g., `bg_code`, `div_code` from the order)
3. Set ContextVar from the extracted tenant context
4. Process the webhook with the resolved tenant context
5. If tenant context cannot be resolved from the payload: return HTTP 400 with `TENANT_CONTEXT_MISSING`

**FORBIDDEN:** Webhook handlers MUST NOT read tenant context from `request.auth` or JWT claims — webhooks are not JWT-authenticated.

---

## Tenant Hierarchy

```
BusinessGroup (legal entity, tax identity)
├── Division (operational brand + business type)
│   ├── Branch (physical outlet)
│   │   └── BankAccount (per BG, referenced by branches)
│   └── DivisionAddress (bill/ship/registered)
```

### Cascade-Code Primary Keys

All tenant tables use cascade codes as natural PKs. This eliminates surrogate IDs and makes tenant context self-contained in the code itself.

| Model | PK Field | Format | Example |
|-------|----------|--------|---------|
| `BusinessGroup` | `bg_code` | `{First4LegalName}{seq}` | `KURO0001` |
| `Division` | `div_code` | `{bg_code}_{seq}` | `KURO0001_001` |
| `Branch` | `branch_code` | `{div_code}_{seq}` | `KURO0001_001_001` |
| `BankAccount` | `bank_code` | `{bg_code}_BK_{seq}` | `KURO0001_BK_001` |
| `DivisionAddress` | `address_code` | `{div_code}_{type}_{seq}` | `KURO0001_001_BILL_001` |

**Why cascade codes:** A `branch_code` of `KURO0001_001_001` tells you the BG, Division, and Branch position without any join. This is critical for MongoDB documents where FK constraints don't exist.

### Current Data

| Level | Count | Examples |
|-------|-------|---------|
| BusinessGroups | 2 | `KURO0001` (KURO CADENCE LLP), `DUNE0003` (DUNE LABS LLP) |
| Divisions | 4 | `KURO0001_001` (Kuro Gaming), `_002` (Rebellion), `_003` (RenderEdge), `DUNE0003_001` (Rebellion) |
| Branches | 6 | Across all divisions |

---

## Tenant Isolation Strategy

### PostgreSQL: Row-Level Security

RLS enforces tenant isolation at the database level. The middleware sets session variables on every request; PostgreSQL silently filters every query to match the current tenant.

**Session variables (set by `TenantContextMiddleware`):**

| Variable | Source (JWT claim) | Purpose |
|----------|-------------------|---------|
| `app.current_bg_code` | `bg_code` | Tenant scope (required, MUST be non-empty) |
| `app.current_division` | `active_div_code` | Active division scope (singular) |
| `app.current_branch` | `active_branch_code` | Active branch scope (singular) |
| `app.current_userid` | `identity_id` | User identity |

**Extraction contract:** The middleware MUST extract claims from the JWT using the exact canonical names above. The middleware MUST NOT read legacy field names (`entity`, `branches`, `userid`) from the JWT.

**Error behavior:** If any required claim (`bg_code`, `identity_id`) is missing or empty, the middleware MUST raise `TenantContextMissing` and abort the request with HTTP 401.

**Policy structure (per table):**

1. `bypass_tenant_isolation_*` — superusers bypass RLS (migrations, admin)
2. `tenant_isolation_*` — `WHERE bg_code = current_setting('app.current_bg_code')`

The `plat/tenant/rls.py` module enables/disables policies. Management command: `python manage.py enable_rls`.

### MongoDB: Three-Layer Enforcement

MongoDB has no built-in RLS. KungOS uses three layers:

**Layer 1 — `TenantCollection` wrapper (application-level):**
All MongoDB access goes through `TenantCollection`, which injects `bg_code` into every read/write and raises `TenantContextMissing` if no active context.

**TenantCollection extraction contract:**
- MUST read `bg_code` from the canonical ContextVar field
- MUST read `div_codes` and `branch_codes` from the canonical ContextVar fields
- MUST NOT read legacy ContextVar keys (`entity`, `branches`) — these are legacy middleware field names, not JWT claims
- MUST inject `bg_code` into every query filter
- MUST raise `TenantContextMissing` if `bg_code` is empty

**Layer 2 — Schema validation (database-level):**
JSON Schema validation on all collections requires `bg_code` as a mandatory field. Prevents orphan documents without tenant context. Management command: `python manage.py mongo_schema_validate`.

**Layer 3 — Tenant-filtered views (read-only enforcement):**
MongoDB views with `$match: {bg_code: {$ne: ""}}` pipeline for read-heavy collections. Queries against the view always include tenant filter. Management command: `python manage.py mongo_create_views`.

---

## Session Tenant Context

The `UserTenantContext` model (`users/models.py`) tracks the active tenant scope for each user session:

```
UserTenantContext
├── userid          — the user (FK → CustomUser.userid)
├── bg_code         — current business group
├── div_codes       — JSON list of accessible division codes (div_codes[0] is active division)
├── branch_codes    — JSON list of accessible branch codes (branch_codes[0] is active branch)
├── token_key       — JWT token for the session (deprecated — see P3-2)
└── scope           — 'full' | 'division' | 'branch'
```

**Active-context convention:** `div_codes[0]` is always the active division. `branch_codes[0]` is always the active branch. The JWT claims `active_div_code` and `active_branch_code` are explicit aliases — they MUST always equal `div_codes[0]` and `branch_codes[0]`.

**Field names:** The Django model uses `div_codes` and `branch_codes` (canonical). The live migration (`users/migrations/0001_initial.py`) already uses these names. Legacy field names (`division`, `branches`) are NOT used in the model.

**Update semantics:** `UserTenantContext` is created on login and updated by tenant switch endpoints (`/api/v1/tenant/switch/`, legacy `/api/v1/users/bgswitch/`). The JWT is the authoritative source — `UserTenantContext` is the persistence layer.

**Relationship to JWT:**
- The JWT is regenerated on every switch endpoint call (see `endpoint_contract_spec.md` §5.3)
- The JWT claims are derived from `UserTenantContext` at generation time
- The JWT is the request-time source of truth
- `UserTenantContext` is the persistence layer — read by `resolve_access` as fallback when JWT is unavailable

---

## Middleware Stack

Two middleware classes enforce tenant context at the request level:

```python
MIDDLEWARE = [
    # ... standard Django middleware ...
    'plat.observability.middleware.CorrelationIDMiddleware',
    'plat.observability.middleware.TenantContextMiddleware',
]
```

- **`CorrelationIDMiddleware`** — Generates `X-Request-ID` for request tracing
- **`TenantContextMiddleware`** — Extracts tenant scope from JWT and populates ContextVar

### TenantContextMiddleware — Detailed Contract

**Input:** JWT from `request.auth` (DRF authentication result)

**Extraction (MUST use canonical names):**
```python
bg_code = token.get("bg_code")
div_codes = token.get("div_codes", [])
branch_codes = token.get("branch_codes", [])
active_div_code = token.get("active_div_code", "")
active_branch_code = token.get("active_branch_code", "")
identity_id = token.get("identity_id", "")
scope = token.get("scope", "full")
```

**Output (ContextVar):**
```python
set_tenant_context({
    "bg_code": bg_code,
    "div_codes": div_codes,
    "branch_codes": branch_codes,
    "active_div_code": active_div_code,
    "active_branch_code": active_branch_code,
    "identity_id": identity_id,
    "scope": scope,
})
```

**Session variables (MUST set on every request):**
```python
SET app.current_bg_code = %s    -- bg_code
SET app.current_division = %s   -- active_div_code
SET app.current_branch = %s     -- active_branch_code
SET app.current_userid = %s     -- identity_id
```

**Error behavior:**
- If `bg_code` is missing or empty: raise `TenantContextMissing`, return HTTP 401
- If `identity_id` is missing or empty: raise `TenantContextMissing`, return HTTP 401
- If `div_codes` or `branch_codes` is missing: set to empty list (non-blocking)

---

## Platform Tenant Module (`plat/tenant/`)

| File | Purpose |
|------|---------|
| `collection.py` | `TenantCollection` — auto-injects `bg_code` into MongoDB queries |
| `config.py` | Tenant configuration loading |
| `exceptions.py` | `TenantContextMissing` exception |
| `rls.py` | Row-level security utilities |
| `verify.py` | Tenant verification helpers |

---

## Architecture Decisions

### Why Shared Database, Not Separate Databases?

All tenants share a single PostgreSQL database and a single MongoDB database. Low tenant count (2 BGs, 4 divisions) makes separate databases unnecessary overhead. Cross-tenant queries for financial reporting and audit require shared storage. MongoDB's own multi-tenant recommendation for moderate tenant counts is shared collections with discriminator fields.

### Why Cascade Codes, Not UUIDs?

Natural cascade codes as PKs, not surrogate UUIDs. `KURO0001_001_001` encodes hierarchy without joins. MongoDB documents reference tenant codes directly (no FK lookups). Changes are traceable by code, not opaque ID. Codes are not globally unique across naming schemes — acceptable because the system controls code generation.

### Why RLS, Not Just Application-Level Filtering?

Application-level filtering is the first line of defense. RLS is the safety net — it enforces tenant isolation at the database level, preventing data leaks even if application code misses a filter.

### Why JWT as Source of Truth?

The JWT travels with every request. It is the only consistent source of tenant context across all layers (middleware, views, services, DB). Using the JWT avoids:
- Race conditions between JWT and DB
- Extra DB queries on every request
- Inconsistency between middleware and application code

---

## Anti-Patterns

| Anti-Pattern | Why It's Bad | Fix |
|--------------|--------------|-----|
| Missing `bg_code` filter on MongoDB queries | Cross-tenant data leak | Use `TenantCollection` wrapper |
| Hardcoded tenant codes | Breaks when new tenants are added | Extract from JWT/session context |
| JSON tenant fields without indexes | Full collection scans | Add compound indexes on `(bg_code, div_code)` |
| `division` as string instead of `div_code` FK | No referential integrity | Use FK to `tenant_divisions.div_code` |
| Inconsistent field naming | Query bugs, maintenance complexity | Canonical: `bg_code`, `div_code`, `branch_code` |
| Reading legacy middleware field names (`entity`, `branches`, `userid`) instead of JWT claims (`div_codes`, `branch_codes`, `identity_id`) | Silent cross-tenant data leakage | Use canonical JWT claims: `div_codes`, `branch_codes`, `identity_id` |
| Switching tenant context without calling backend | Frontend/Backend state drift | Frontend MUST call `/api/v1/tenant/switch/` on tenant change |

---

## Cross-References

- `CANONICAL_NAMING.md` — frozen canonical names
- `endpoint_contract_spec.md` §5 — tenant context rules, switch endpoint contract
- `endpoint_contract_spec.md` §11.1 — legacy → canonical field mapping
- `postgresql_schema.md` §4 — tenant schema (LIVE = TARGET)
- `mongodb_schema.md` §2 — MongoDB tenant field naming
- `identity_layer.md` — unified identity architecture
- `rbac_system.md` — RBAC resolution engine

---

> **Implementation state:** Tenant hierarchy, cascade codes, RLS policies, TenantCollection wrapper, schema validation, and MongoDB views are implemented. Middleware extraction bug (legacy field names) is tracked in `tenant-context-audit_a72921.md` (P0). Switch endpoint JWT emission is tracked as P1. Session context tracking and field naming alignment are tracked in `operations/`.
