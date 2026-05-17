# Migration Specification — Current to Target State

**Status:** Spec — Phase 4–8  
**Date:** 2026-05-17  
**Source:** `KungOS_Identity_Design.md`, `alignment_audit.md`, `kungos_v2_db.md`  
**Purpose:** Authoritative migration blueprint for all database changes (current → target)

---

## 1. Migration Inventory

| Migration | Phase | Scope | Risk | Status |
|---|---|---|---|---|
| **M1: Identity consolidation** | 4 | 7 user types → `users_identity` + 5 extensions | **HIGH** | Not started |
| **M2: Cafe schema alignment** | 4 | Walk-in → identity FK, wallet → identity FK | **MEDIUM** | Migrations 0001-0003 unapplied |
| **M3: MongoDB field rename** | 5.7 | `bgcode` → `bg_code`, `division` → `div_code` | **HIGH** | Not started |
| **M4: Orders to PostgreSQL** | 8 | 4 Mongo collections → `orders_core` + 6 detail tables | **HIGH** | Not started |
| **M5: Gaming collections** | 3b | 12 gaming collections → `KungOS_Mongo_One` | **MEDIUM** | Not started |

---

## 2. M1: Identity Consolidation

### 2.1 Scope

Merge 7 user types from 8 storage locations into `users_identity` + 5 extension tables.

| Source | Records | Target | Dedup Strategy |
|---|---|---|---|
| `reb_users` (Mongo) | 1,979 | `users_identity` + `users_customer` | Phone normalization, E.164 |
| `misc` (Mongo) | 1,979 | **SKIP** (100% duplicate of `reb_users`) | — |
| `players` (Mongo) | 117 (59 unique) | `users_identity` + `users_player` | Phone + name fuzzy match |
| `employee_attendance` (Mongo) | 966 (31 unique) | `users_identity` + `users_employee` | Cross-ref `CustomUser.phone` |
| `KuroUser` (PG) | 31 | `users_employee` | Merge into employee records |
| `serviceRequest` (Mongo) | 1,328 | `users_identity` + `users_customer` | Phone normalization |
| `orders.user.phone` (Mongo) | 727 | `users_identity` + `users_customer` | Phone normalization |
| `teams` (Mongo) | 14 | `users_organization` + `users_team_profile` | Direct import |
| `vendors` (Mongo) | 409 | `users_organization` + `users_vendor_profile` | Direct import |

### 2.2 Dedup Strategy

**Step 1: Normalize all phone numbers to E.164 (`+91XXXXXXXXXX`)**

```python
def normalize_phone(raw_phone: str, region: str = 'IN') -> str:
    """Normalize phone to E.164 format."""
    cleaned = re.sub(r'[^\d+]', '', raw_phone)
    parsed = phonenumbers.parse(cleaned, region)
    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
```

**Step 2: Group by normalized phone**

**Step 3: Conflict resolution**

| Scenario | Action | Confidence |
|---|---|---|
| Same phone + same name | Auto-merge | 99% |
| Same phone + fuzzy name (>85%) | Merge with warning | 85-98% |
| Same phone + different name (<85%) | Flag for manual review | <85% |
| Name match but no phone match | Flag for manual review | — |

**Step 4: Cross-reference merges**

- `serviceRequest.phone` ↔ `reb_users.phone` (30 matches → `is_requestor=True`)
- `players.mobile` ↔ `reb_users.phone` (12 matches → dual: `player_profile` + `customer_profile`)
- `orders.user.phone` ↔ `reb_users.phone` (73% match → `registered=False` for 727 unregistered)
- `employee_attendance.userid` ↔ `CustomUser.phone` (31 matches → `employee_profile`)

### 2.3 Migration Command

```
python manage.py migrate_identity --source=<mongo_uri> --validate
```

**Validation gates:**

```
✅ Row count reconciliation per source:
   reb_users: 1979 source → 1979 output (0 dropped)
   players: 117 source → 59 output (58 duplicates merged)
   employees: 31 source → 31 output (0 dropped)
   vendors: 409 source → 409 output (0 dropped)
   teams: 14 source → 14 output (0 dropped)

✅ Phone normalization: 0 invalid numbers
✅ Dedup review: 12 rows flagged (manual resolution required)
✅ Phone uniqueness per tenant: 0 duplicates
✅ FK integrity: 0 orphaned extension rows
✅ CafeWalkin.identity FK coverage: 0 NULLs
✅ Tenant codes: 0 invalid bg_code/div_code
✅ Auth linkage: 0 phone-only identities with CustomUser
✅ Financial data loss check: total_spent sum matches legacy orders
✅ Index creation: all indexes built
✅ Constraint validation: all CHECK constraints pass
```

### 2.4 Deployment Steps

1. Apply Django migrations (create empty tables + indexes)
2. Run `migrate_identity` management command (import + dedup)
3. Run `--validate` flag (row count checks, phone normalization checks)
4. Deploy application code (all views use new Identity models)
5. Verify health checks + smoke tests
6. Legacy MongoDB collections remain untouched (eventual cleanup, not blocking)

### 2.5 Rollback Strategy

- **Pre-migration backup:** Full PostgreSQL dump + MongoDB dump
- **Rollback command:** `python manage.py rollback_identity` (drops new tables, restores legacy models)
- **Rollback approval:** Requires Modernization Owner approval

---

## 3. M2: Cafe Schema Alignment

### 3.1 Scope

Align cafe platform tables with `users_identity`.

| Change | Table | Current | Target |
|---|---|---|---|
| Walk-in identity | `caf_platform_walkins` | `phone` UNIQUE | `identity_id` FK → `users_identity` |
| Wallet binding | `caf_platform_wallets` | `customer_id` FK → `CustomUser` | `identity_id` FK → `users_identity` |
| Cafe users | `caf_platform_users` | Thin projection of `CustomUser` | **REPLACED** by `users_identity` |

### 3.2 Migration Steps

**Step 1: Backfill walk-in identities**

```sql
UPDATE caf_platform_walkins
SET identity_id = (
    SELECT i.identity_id
    FROM users_identity i
    WHERE i.phone = caf_platform_walkins.phone
)
WHERE identity_id IS NULL;
```

**Step 2: Drop phone uniqueness**

```sql
ALTER TABLE caf_platform_walkins
DROP CONSTRAINT caf_platform_walkins_phone_key;
```

**Step 3: Add identity FK**

```sql
ALTER TABLE caf_platform_walkins
ALTER COLUMN identity_id SET NOT NULL;

ALTER TABLE caf_platform_walkins
ADD CONSTRAINT fk_walkin_identity
FOREIGN KEY (identity_id) REFERENCES users_identity(identity_id);
```

**Step 4: Migrate wallet binding**

```sql
UPDATE caf_platform_wallets
SET identity_id = (
    SELECT i.identity_id
    FROM users_identity i
    JOIN users_customuser c ON i.user = c.userid
    WHERE c.userid = caf_platform_wallets.customer_id
)
WHERE identity_id IS NULL;

ALTER TABLE caf_platform_wallets
DROP CONSTRAINT fk_wallet_customer;

ALTER TABLE caf_platform_wallets
ADD CONSTRAINT fk_wallet_identity
FOREIGN KEY (identity_id) REFERENCES users_identity(identity_id);
```

**Step 5: Replace cafe users**

```sql
-- Migrate cafe user data to users_identity
INSERT INTO users_identity (identity_id, phone, name, bg_code, div_code, user)
SELECT
    'ID' || LPAD(ROW_NUMBER() OVER (), 6, '0'),
    cu.phone,
    cu.name,
    'KURO0001',  -- default BG
    'KURO0001_001',  -- default division
    cu.userid
FROM caf_platform_users cu
LEFT JOIN users_identity i ON i.phone = cu.phone
WHERE i.identity_id IS NULL;

-- Drop caf_platform_users table
DROP TABLE caf_platform_users;
```

### 3.3 Unapplied Migrations

Migrations 0001-0003 are unapplied. They sync live PostgreSQL schema with target models.

---

## 4. M3: MongoDB Field Rename (Phase 5.7)

### 4.1 Scope

Rename `bgcode` → `bg_code`, `division` → `div_code`, `branch` → `branch_code` across all 31 collections.

### 4.2 Migration Strategy

**Phase 1: Dual-read middleware**

Support both legacy and canonical field names during transition. Middleware checks for `bg_code` first, falls back to `bgcode`.

```python
# Dual-read middleware
def get_tenant_field(document, canonical_field, legacy_field):
    """Get tenant field with dual-read support."""
    return document.get(canonical_field) or document.get(legacy_field)
```

**Phase 2: Batch migration**

Process collections in batches (1000 docs/batch) to avoid locking.

```python
# Batch migration
batch_size = 1000
for collection in collections:
    cursor = collection.find({})
    batch = []
    for doc in cursor:
        if 'bgcode' in doc:
            doc['bg_code'] = doc.pop('bgcode')
        if 'division' in doc:
            doc['div_code'] = doc.pop('division')
        if 'branch' in doc:
            doc['branch_code'] = doc.pop('branch')
        batch.append(doc)

        if len(batch) >= batch_size:
            collection.update_many(
                {'_id': {'$in': [b['_id'] for b in batch]}},
                [{'$set': {'bg_code': {'$pop': 1}}}],  # example
                upsert=True
            )
            batch = []
```

**Phase 3: Index rebuild**

Drop legacy indexes, create canonical indexes.

```javascript
// Drop legacy index
db.collection.dropIndex({ bgcode: 1, division: 1 })

// Create canonical index
db.collection.createIndex({ bg_code: 1, div_code: 1 })
```

**Phase 4: Schema validation**

Enable JSON Schema validation after migration completes.

```javascript
db.createCollection("kgorders", {
   validator: {
      $jsonSchema: {
         bsonType: "object",
         required: [ "bg_code", "div_code", "orderid" ],
         properties: {
            bg_code: { bsonType: "string", pattern: "^[A-Z]{4}\\d{4}$" },
            div_code: { bsonType: "string", pattern: "^[A-Z]{4}\\d{4}_\\d{3}$" }
         }
      }
   }
});
```

**Phase 5: Rollback**

Legacy field names preserved until dual-read middleware is removed. If migration fails, rollback to legacy field names.

### 4.3 Validation Gates

```
python manage.py mongo_field_migration --validate

✅ Field rename: 0 documents with legacy field names
✅ Index creation: all canonical indexes built
✅ Schema validation: all collections pass JSON Schema
✅ Tenant isolation: 0 documents without bg_code
✅ Compound indexes: 31/31 collections have (bg_code, div_code) index
```

---

## 5. M4: Orders to PostgreSQL (Phase 8)

### 5.1 Scope

Migrate 4 MongoDB collections to PostgreSQL `orders_core` + 6 detail tables.

| Source | Records | Target | Notes |
|---|---|---|---|
| `estimates` | — | `orders_core` + `estimate_detail` | |
| `kgorders` | — | `orders_core` + `in_store_detail` | |
| `tporders` | — | `orders_core` + `tp_order_detail` | |
| `serviceRequest` | 1,625 | `orders_core` + `service_detail` | |

**Total:** 15,925 docs

### 5.2 Migration Strategy

1. **Create empty PostgreSQL tables** (migrations)
2. **Read MongoDB collections** (batch processing)
3. **Normalize data** (phone → `identity_id`, tenant codes → canonical)
4. **Write to PostgreSQL** (batch inserts, transaction-per-batch)
5. **Validate** (row count reconciliation, data integrity checks)
6. **Deploy application code** (all views use new order models)
7. **Legacy MongoDB collections** remain untouched (eventual cleanup)

### 5.3 Validation Gates

```
python manage.py migrate_orders --validate

✅ Row count reconciliation:
   estimates: X source → X output (0 dropped)
   kgorders: X source → X output (0 dropped)
   tporders: X source → X output (0 dropped)
   serviceRequest: 1625 source → 1625 output (0 dropped)

✅ FK integrity: 0 orphaned order rows
✅ Tenant codes: 0 invalid bg_code/div_code
✅ Customer linkage: 0 orders without customer_id
✅ Financial data loss check: total_amount sum matches legacy
✅ Index creation: all indexes built
✅ Constraint validation: all CHECK constraints pass
```

---

## 6. M5: Gaming Collections (Phase 3b)

### 6.1 Scope

Integrate 12 gaming collections from `kuro-gaming-dj-backend` into `KungOS_Mongo_One`.

| Collection | Purpose | Notes |
|---|---|---|
| `prods` | Product catalog | |
| `builds` | Pre-built PC builds | |
| `kgbuilds` | Kuro Gaming builds | |
| `custombuilds` | Custom PC builds (ordered) | Immutable copies |
| `components` | Hardware components | |
| `accessories` | PC accessories | |
| `monitors` | Monitor catalog | |
| `networking` | Networking equipment | |
| `external` | External products | |
| `games` | Game catalog | |
| `kurodata` | CMS content | |
| `lists` | Preset lists | |
| `presets` | Preset configurations | |

### 6.2 Migration Strategy

1. **Export gaming collections** from `kuro-gaming-dj-backend` database
2. **Add tenant fields** (`bg_code`, `div_code`, `branch_code`) to all documents
3. **Import into `KungOS_Mongo_One`** (batch processing)
4. **Create indexes** (tenant compound indexes, query indexes)
5. **Enable schema validation** (JSON Schema requires tenant fields)
6. **Deploy application code** (gaming views use `TenantCollection` wrapper)
7. **Verify** (row count reconciliation, tenant field coverage)

---

## 7. Migration Dependencies

```
M1: Identity consolidation (Phase 4)
├── Required before: M2 (Cafe schema alignment)
├── Required before: M4 (Orders to PostgreSQL)
└── Independent of: M3 (MongoDB field rename), M5 (Gaming collections)

M2: Cafe schema alignment (Phase 4)
├── Depends on: M1 (Identity consolidation)
└── Independent of: M3, M4, M5

M3: MongoDB field rename (Phase 5.7)
├── Independent of: M1, M2, M4, M5
└── Required before: Phase 4 completion (tenant isolation)

M4: Orders to PostgreSQL (Phase 8)
├── Depends on: M1 (Identity consolidation) — for customer_id linkage
└── Independent of: M2, M3, M5

M5: Gaming collections (Phase 3b)
├── Depends on: Phase 1 (tenant context, MongoDB consolidation)
└── Independent of: M1, M2, M3, M4
```

---

## 8. Rollback Strategy

### 8.1 General Rollback Principles

- **Pre-migration backup:** Full PostgreSQL dump + MongoDB dump before each migration
- **Rollback approval:** Requires Modernization Owner approval
- **Rollback path:** Git revert + database backup restore
- **No canary deployment:** Single deployment at end of program

### 8.2 Migration-Specific Rollback

| Migration | Rollback Command | Rollback Scope |
|---|---|---|
| M1: Identity | `python manage.py rollback_identity` | Drop new tables, restore legacy models |
| M2: Cafe | `python manage.py rollback_cafe` | Restore walk-in phone uniqueness, wallet FK |
| M3: MongoDB | `python manage.py rollback_mongo_fields` | Restore legacy field names |
| M4: Orders | `python manage.py rollback_orders` | Drop new tables, restore Mongo collections |
| M5: Gaming | `python manage.py rollback_gaming` | Remove gaming collections from `KungOS_Mongo_One` |

---

> **Implementation state:** No migrations have been executed. M1-M5 are planned. M2 migrations 0001-0003 are unapplied. All migrations require Modernization Owner approval before execution.
