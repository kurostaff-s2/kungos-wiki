# MongoDB Schema Specification

**Status:** Spec — LIVE vs TARGET  
**Date:** 2026-05-17  
**Source:** `kungos_v2_db.md` (verified 2026-04-29), `multi_tenancy.md`  
**Purpose:** Authoritative reference for all MongoDB collections, tenant fields, indexes, naming conventions

---

## 1. Database Overview

| Aspect | Value |
|---|---|
| **Database name** | `KungOS_Mongo_One` |
| **Total collections** | 31 LIVE + 12 e-commerce product (deferred to Phase 3b) |
| **Total documents** | 68,443 |
| **Tenant scoping** | 100% — all 31 collections have `(bgcode, division, branch)` fields |
| **Tenant indexes** | 31/31 collections have `(bgcode, division)` compound index |
| **Schema validation** | JSON Schema requires `bg_code` (canonical) on all collections |
| **RLS equivalent** | `TenantCollection` wrapper + schema validation + tenant-filtered views |

---

## 2. Tenant Field Naming — LIVE vs TARGET

### 2.1 The Naming Skew (Critical Gap)

| Field | LIVE (MongoDB) | TARGET (Canonical) | Risk |
|---|---|---|---|
| Business group | `bgcode` | `bg_code` | **HIGH** — `TenantCollection` injects `bg_code`; legacy collections use `bgcode` |
| Division | `division` | `div_code` | **HIGH** — mismatch with PG `div_code` FK |
| Branch | `branch` | `branch_code` | **MEDIUM** — inconsistency with PG `branch_code` |

**Security impact:** If a developer uses `TenantCollection` wrapper but queries a legacy collection with `bgcode` instead of `bg_code`, the tenant isolation filter fails silently → **cross-tenant data exposure**.

### 2.2 Resolution (Phase 5.7)

**Migration:** Rename `bgcode` → `bg_code`, `division` → `div_code`, `branch` → `branch_code` across all 31 collections.

**Guardrails:**
1. JSON Schema validation rejects documents missing canonical fields
2. `TenantCollection` wrapper injects canonical `bg_code`
3. Legacy field names (`bgcode`, `division`) are blocked by schema validation
4. Dual-read middleware supports both field names during transition period

---

## 3. Collection Inventory — LIVE (31 collections)

### 3.1 Identity Collections (5) — TARGET: Deprecated

| Collection | Docs | Purpose | TARGET |
|---|---|---|---|
| `reb_users` | 1,982 | Rebellion users | → `users_identity` + `users_customer` (PG) |
| `misc` | 3,218 | 100% duplicate of `reb_users` | → DEDUPLICATED into `users_identity` |
| `players` | 117 | Esports players (50% dup) | → `users_identity` + `users_player` (PG) |
| `vendors` | 409 | Vendor records | → `users_organization` + `users_vendor_profile` (PG) |
| `teams` | 14 | Esports teams | → `users_organization` + `users_team_profile` (PG) |

**Anti-patterns:**
- No referential integrity — `reb_users.userid` can reference a deleted `CustomUser`
- No phone normalization — `+91 98765 43210` ≠ `9876543210`
- No transactional consistency — writing to `reb_users` and `CustomUser` is two independent operations
- Tenant filtering — `bgcode` field exists but no compound index on `(bgcode, phone)`

### 3.2 Orders Collections (4) — TARGET: PostgreSQL `orders_core` + detail tables

| Collection | Docs | Purpose | TARGET |
|---|---|---|---|
| `estimates` | — | Sales estimates | → `orders_core` + `estimate_detail` (PG) |
| `kgorders` | — | In-store orders (F&B) | → `orders_core` + `in_store_detail` (PG) |
| `tporders` | — | Third-party orders | → `orders_core` + `tp_order_detail` (PG) |
| `serviceRequest` | 1,625 | Service requests | → `orders_core` + `service_detail` (PG) |

**Migration:** 15,925 docs from 4 Mongo collections → core + detail tables. See `orders-migration-plan.md`.

### 3.3 Operational Collections (10)

| Collection | Docs | Purpose | Notes |
|---|---|---|---|
| `employee_attendance` | 966 | Employee attendance records | `userid` → `identity_id` (TARGET) |
| `inwardpayments` | — | Inward payment records | Financial audit trail |
| `outwardpayments` | — | Outward payment records | Financial audit trail |
| `inwardinvoices` | — | Inward invoices | Financial audit trail |
| `outwardinvoices` | — | Outward invoices | Financial audit trail |
| `inwardcreditnotes` | — | Inward credit notes | Financial audit trail |
| `inwarddebitnotes` | — | Inward debit notes | Financial audit trail |
| `outwardcreditnotes` | — | Outward credit notes | Financial audit trail |
| `outwarddebitnotes` | — | Outward debit notes | Financial audit trail |
| `indentproduct` | — | Procurement indents | Stays in MongoDB — flexible schema needed |

### 3.4 Product/Inventory Collections (7)

| Collection | Docs | Purpose | Notes |
|---|---|---|---|
| `products` | — | Product catalog | |
| `stock` | — | Stock levels | |
| `purchases` | — | Purchase records | |
| `purchase_orders` | — | Purchase orders | |
| `sales` | — | Sales records | |
| `inventory` | — | Inventory tracking | |
| `offline_orders` | — | Offline orders | |

### 3.5 HR/Teams Collections (3)

| Collection | Docs | Purpose | Notes |
|---|---|---|---|
| `employees` | — | Employee records | |
| `empadminlist` | — | Employee admin list | |
| `empdashlist` | — | Employee dashboard list | |

### 3.6 Other Collections (2)

| Collection | Docs | Purpose | Notes |
|---|---|---|---|
| `audit` | — | Audit trail | |
| `export_data` | — | Export data | |

---

## 4. E-Commerce Product Collections — TARGET (Phase 3b, Deferred)

12 collections from `kuro-gaming-dj-backend` (legacy e-commerce backend):

| Collection | Purpose | Notes |
|---|---|---|
| `prods` | Product catalog | |
| `builds` | Pre-built PC builds | |
| `kgbuilds` | Kuro Gaming builds | |
| `custombuilds` | Custom PC builds (ordered) | Immutable copies of ordered builds |
| `components` | Hardware components | |
| `accessories` | PC accessories | |
| `monitors` | Monitor catalog | |
| `networking` | Networking equipment | |
| `external` | External products | |
| `games` | Game catalog | |
| `kurodata` | CMS content (hero banners) | |
| `lists` | Preset lists | |
| `presets` | Preset configurations | |

**Note:** These collections are MISSING from `KungOS_Mongo_One`. They exist in the legacy e-commerce backend's separate database. Integration deferred to Phase 3b.

---

## 5. Tenant Enforcement — Three Layers

### 5.1 Layer 1: `TenantCollection` Wrapper (Application-Level)

All MongoDB access goes through `TenantCollection`, which injects `bg_code` into every read/write and raises `TenantContextMissing` if no active context.

```python
# plat/tenant/collection.py
class TenantCollection:
    def __init__(self, collection, context):
        self._collection = collection
        self._context = context

    def find(self, filter, *args, **kwargs):
        if not self._context.bg_code:
            raise TenantContextMissing("Queries blocked without active bg_code context.")
        filter = filter.copy()
        filter['bg_code'] = self._context.bg_code
        return self._collection.find(filter, *args, **kwargs)

    def insert_one(self, document, *args, **kwargs):
        if not self._context.bg_code:
            raise TenantContextMissing("Writes blocked without active bg_code context.")
        document['bg_code'] = self._context.bg_code
        return self._collection.insert_one(document, *args, **kwargs)
```

**Anti-pattern:** Raw PyMongo calls bypass this layer. All views must route through `get_collection()` helper.

### 5.2 Layer 2: JSON Schema Validation (Database-Level)

JSON Schema validation on all collections requires `bg_code` as a mandatory field. Prevents orphan documents without tenant context.

```javascript
db.createCollection("kgorders", {
   validator: {
      $jsonSchema: {
         bsonType: "object",
         required: [ "bg_code", "div_code", "orderid" ],
         properties: {
            bg_code: { bsonType: "string", pattern: "^[A-Z]{4}\\d{4}$" },
            div_code: { bsonType: "string", pattern: "^[A-Z]{4}\\d{4}_\\d{3}$" }
         },
         additionalProperties: true
      }
   }
});
```

**Management command:** `python manage.py mongo_schema_validate`

### 5.3 Layer 3: Tenant-Filtered Views (Read-Only Enforcement)

MongoDB views with `$match: {bg_code: {$ne: ""}}` pipeline for read-heavy collections. Queries against the view always include tenant filter.

**Management command:** `python manage.py mongo_create_views`

---

## 6. Index Strategy

### 6.1 Tenant Compound Indexes

All 31 collections have compound indexes on `(bgcode, division)` (LIVE) → `(bg_code, div_code)` (TARGET).

```javascript
// LIVE (legacy naming)
db.collection.createIndex({ bgcode: 1, division: 1 })

// TARGET (canonical naming)
db.collection.createIndex({ bg_code: 1, div_code: 1 })
```

### 6.2 Identity Collection Indexes

| Collection | Index | Purpose |
|---|---|---|
| `reb_users` | `(bgcode, phone)` | Tenant-scoped phone lookup |
| `players` | `(bgcode, playerid)` | Tenant-scoped player lookup |
| `vendors` | `(bgcode, gstin)` | Tenant-scoped vendor lookup |
| `employee_attendance` | `(bgcode, userid)` | Tenant-scoped attendance lookup |

**TARGET:** All indexes renamed to canonical field names during Phase 5.7 migration.

### 6.3 Order Collection Indexes

| Collection | Index | Purpose |
|---|---|---|
| `kgorders` | `(bgcode, orderid)` | Tenant-scoped order lookup |
| `tporders` | `(bgcode, orderid)` | Tenant-scoped order lookup |
| `estimates` | `(bgcode, estimateid)` | Tenant-scoped estimate lookup |
| `serviceRequest` | `(bgcode, sr_no)` | Tenant-scoped service request lookup |

---

## 7. Connection Management

### 7.1 Singleton Pattern

`get_collection()` uses a singleton `get_mongo_client()`. All `MongoClient()` calls outside `management/commands/` route through the singleton.

**Why singleton:** Prevents connection pool exhaustion. Multiple `MongoClient()` instances each create their own connection pool. A singleton shares one pool across all requests.

### 7.2 Anti-Patterns

| Anti-Pattern | Why It's Bad | Fix |
|---|---|---|
| Direct `MongoClient()` in views | Connection pool exhaustion | Use `get_collection()` singleton |
| Missing `bg_code` filter | Cross-tenant data leak | Use `TenantCollection` wrapper |
| Hardcoded tenant codes | Breaks when new tenants added | Extract from JWT/session context |
| JSON fields without indexes | Full collection scans | Add compound indexes on `(bg_code, div_code)` |
| Inconsistent field naming | Query bugs, maintenance complexity | Canonical: `bg_code`, `div_code`, `branch_code` |

---

## 8. Migration Plan — Phase 5.7

### 8.1 Field Rename Migration

**Scope:** Rename `bgcode` → `bg_code`, `division` → `div_code`, `branch` → `branch_code` across all 31 collections.

**Strategy:**
1. **Dual-read middleware** — supports both legacy and canonical field names during transition
2. **Batch migration** — process collections in batches (1000 docs/batch) to avoid locking
3. **Index rebuild** — drop legacy indexes, create canonical indexes
4. **Schema validation** — enable JSON Schema validation after migration completes
5. **Rollback** — legacy field names preserved until dual-read middleware is removed

### 8.2 Validation Gates

```
python manage.py mongo_field_migration --validate

✅ Field rename: 0 documents with legacy field names
✅ Index creation: all canonical indexes built
✅ Schema validation: all collections pass JSON Schema
✅ Tenant isolation: 0 documents without bg_code
✅ Compound indexes: 31/31 collections have (bg_code, div_code) index
```

---

## 9. Cross-Reference with PostgreSQL

### 9.1 Identity Cross-Reference

| MongoDB Collection | PostgreSQL Table | Join Key | Status |
|---|---|---|---|
| `reb_users` | `users_identity` + `users_customer` | `phone` → `identity_id` | TARGET: Mongo deprecated |
| `players` | `users_identity` + `users_player` | `mobile` → `identity_id` | TARGET: Mongo deprecated |
| `vendors` | `users_organization` + `users_vendor_profile` | `gstin` → `gstin` | TARGET: Mongo deprecated |
| `employee_attendance` | `users_identity` + `users_employee` | `userid` → `identity_id` | TARGET: field rename |
| `serviceRequest` | `users_identity` + `users_customer` | `phone` → `identity_id` | TARGET: PG `orders_core` |

### 9.2 Order Cross-Reference

| MongoDB Collection | PostgreSQL Table | Join Key | Status |
|---|---|---|---|
| `kgorders` | `orders_core` + `in_store_detail` | `orderid` → `orderid` | TARGET: PG migration |
| `tporders` | `orders_core` + `tp_order_detail` | `orderid` → `orderid` | TARGET: PG migration |
| `estimates` | `orders_core` + `estimate_detail` | `estimateid` → `orderid` | TARGET: PG migration |
| `serviceRequest` | `orders_core` + `service_detail` | `sr_no` → `orderid` | TARGET: PG migration |

---

> **Implementation state:** All 31 collections are LIVE with legacy field names (`bgcode`, `division`). Phase 5.7 migration renames to canonical fields (`bg_code`, `div_code`). E-commerce product collections (12) deferred to Phase 3b. Identity collections (5) deprecated in favor of PostgreSQL `users_identity` + extensions.
