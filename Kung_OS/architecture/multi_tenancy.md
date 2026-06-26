# Multi-Tenancy Architecture

## Canonical Glossary

| Term | Canonical Name | Legacy Name | Description |
|------|---------------|-------------|-------------|
| Business Group | `bg_code` | `bgcode` | Top-level tenant (e.g., `KURO0001`) |
| Division | `div_code` | `division` | Mid-level tenant (e.g., `KURO0001_001`) |
| Branch | `branch_code` | `branch` | Leaf-level tenant (e.g., `KURO0001_001_B01`) |
| Division scope | `div_codes[]` | `division[]` | Array of all accessible divisions (authorization scope) |
| Branch scope | `branch_codes[]` | `branches[]` | Array of all accessible branches (authorization scope) |
| Active division | `active_div_code` | `entity[0]` | Current active division (singular, from scope) |
| Active branch | `active_branch_code` | `branches[0]` | Current active branch (singular, from scope) |
| Identity | `identity_id` | `userid` | Stable person PK (replaces CustomUser PK) |

**Status:** Constitution (stable, long-lived)
**Last updated:** 2026-06-26

---

## JWT Claims Target

| Claim | Type | Source | Description |
|-------|------|--------|-------------|
| `bg_code` | string | active context | Business Group (required) |
| `div_codes` | array[] | authorization scope | All accessible divisions |
| `branch_codes` | array[] | authorization scope | All accessible branches |
| `active_div_code` | string | active context | Current active division |
| `active_branch_code` | string \| null | active context | Current active branch (nullable) |
| `identity_id` | string | `users_identity` | Stable person PK |

**Scope vs active context:** The JWT carries both authorization scope (`div_codes[]`, `branch_codes[]` — all accessible) and active context (`active_div_code`, `active_branch_code` — current selection). Session variables reflect the **active context** (singular), not the full scope.

---

## Principle

KungOS is a shared-database multi-tenant system. All data — PostgreSQL and MongoDB — is tenant-scoped. There are no separate databases per tenant.

### Core Rule

Every query, every write, every aggregation **must** include tenant scope (`bg_code`, optionally `div_code`, optionally `branch_code`). There are no exceptions.

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
|-------|-------|----------|
| BusinessGroups | 2 | `KURO0001` (KURO CADENCE LLP), `DUNE0003` (DUNE LABS LLP) |
| Divisions | 4 | `KURO0001_001` (Kuro Gaming), `_002` (Rebellion), `_003` (RenderEdge), `DUNE0003_001` (Rebellion) |
| Branches | 6 | Across all divisions |

---

## Tenant Isolation Strategy

### PostgreSQL: Row-Level Security

RLS enforces tenant isolation at the database level. The middleware sets session variables on every request;
PostgreSQL silently filters every query to match the current tenant.

**Session variables (set by `TenantContextMiddleware`):**

| Variable | Source | Purpose |
|----------|--------|---------|
| `app.current_bg_code` | JWT `bg_code` | Tenant scope (required) |
| `app.current_division` | JWT `active_div_code` | Active division scope (singular, not array) |
| `app.current_branch` | JWT `active_branch_code` | Active branch scope (singular, not array) |
| `app.current_userid` | JWT `identity_id` (target) / `userid` (legacy) | User identity |

**Scope vs active context:** The JWT carries both authorization scope (`div_codes[]`, `branch_codes[]` -- all accessible) and active context (`active_div_code`, `active_branch_code` -- current selection). Session variables reflect the **active context** (singular), not the full scope. See `endpoint_contract_spec.md` section 11 for the full compatibility matrix.

**Policy structure (per table):**

1. `bypass_tenant_isolation_*` — superusers bypass RLS (migrations, admin)
2. `tenant_isolation_*` — `WHERE bg_code = current_setting('app.current_bg_code')`

The `plat/tenant/rls.py` module enables/disables policies. Management command: `python manage.py enable_rls`.

### MongoDB: Three-Layer Enforcement

MongoDB has no built-in RLS. KungOS uses three layers:

**Layer 1 — `TenantCollection` wrapper (application-level):**
All MongoDB access goes through `TenantCollection`, which injects `bg_code` into every read/write
and raises `TenantContextMissing` if no active context. Raw PyMongo calls bypass this layer.

**Layer 2 — Schema validation (database-level):**
JSON Schema validation on all collections requires `bg_code` as a mandatory field.
Prevents orphan documents without tenant context. Management command: `python manage.py mongo_schema_validate`.

**Layer 3 — Tenant-filtered views (read-only enforcement):**
MongoDB views with `$match: {bg_code: {$ne: ""}}` pipeline for read-heavy collections.
Queries against the view always include tenant filter. Management command: `python manage.py mongo_create_views`.

---

## Session Tenant Context

The `UserTenantContext` model (`users/models.py`) tracks the active tenant scope for each user session:

```
UserTenantContext
├── userid          — the user
├── bg_code         — current business group
├── division        — JSON list of accessible divisions (or all)
├── branches        — JSON list of accessible branches (or all)
├── token_key       — JWT token for the session
├── scope           — 'full' | 'division' | 'branch'
```

**Scope resolution:**
- `full` — user has access to all divisions/branches in the BG
- `division` — user is scoped to specific divisions
- `branch` — user is scoped to specific branches

---

## Platform Tenant Module (`plat/tenant/`)

| File | Purpose |
|------|---------|
| `collection.py` | `TenantCollection` — auto-injects `bg_code` into MongoDB queries |
| `config.py` | Tenant configuration loading |
| `exceptions.py` | Tenant-related exceptions |
| `rls.py` | Row-level security utilities |
| `verify.py` | Tenant verification helpers |

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

- **`CorrelationIDMiddleware`** — Generates `X-Correlation-ID` for request tracing
- **`TenantContextMiddleware`** — Extracts tenant scope from JWT/session and makes it available to views

---

## Architecture Decisions

### Why Shared Database, Not Separate Databases?

All tenants share a single PostgreSQL database and a single MongoDB database. Low tenant count (2 BGs, 4 divisions) makes separate databases unnecessary overhead. Cross-tenant queries for financial reporting and audit require shared storage. MongoDB's own multi-tenant recommendation for moderate tenant counts is shared collections with discriminator fields.

### Why Cascade Codes, Not UUIDs?

Natural cascade codes as PKs, not surrogate UUIDs. `KURO0001_001_001` encodes hierarchy without joins. MongoDB documents reference tenant codes directly (no FK lookups). Changes are traceable by code, not opaque ID. Codes are not globally unique across naming schemes — acceptable because the system controls code generation.

### Why RLS, Not Just Application-Level Filtering?

Application-level filtering is the first line of defense. RLS is the safety net — it enforces tenant isolation at the database level, preventing data leaks even if application code misses a filter.

---

## Anti-Patterns

| Anti-Pattern | Why It's Bad | Fix |
|--------------|--------------|-----|
| Missing `bg_code` filter on MongoDB queries | Cross-tenant data leak | Use `TenantCollection` wrapper |
| Hardcoded tenant codes | Breaks when new tenants are added | Extract from JWT/session context |
| JSON tenant fields without indexes | Full collection scans | Add compound indexes on `(bg_code, div_code)` |
| `division` as string instead of `div_code` FK | No referential integrity | Use FK to `tenant_divisions.div_code` |
| Inconsistent field naming | Query bugs, maintenance complexity | Canonical: `bg_code`, `div_code`, `branch_code` |

---

> **Implementation state:** Tenant hierarchy, cascade codes, RLS policies, TenantCollection wrapper, schema validation, and MongoDB views are implemented. Session context tracking and field naming alignment are tracked in `operations/`.
