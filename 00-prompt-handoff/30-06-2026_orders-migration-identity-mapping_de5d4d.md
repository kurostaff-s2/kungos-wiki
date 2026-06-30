# Orders Migration & Identity Mapping Audit

| Field | Value |
|-------|-------|
| Project ID | `kteam-dj-chief` |
| Primary entity ID | `de5d4d` |
| Entity type | `handoff` |
| Short description | Audit orders migration across 6 source collections, map to identity-based users in `KungOS_PG_One`, and document the clean re-migration strategy with customer_id resolution |
| Status | `draft` |
| Source references | `30-06-2026_user-data-migration-canonical_779286.md`, `30-06-2026_architecture-v15-execution_e02526.md`, `/tmp/migrate_orders.py`, `migrate_legacy_eshop.py` |
| Generated | `30-06-2026` |
| Next action / owner | Execute orders re-migration after user migration (Phase 8-9 in user handoff) |

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Reference docs:**
- `30-06-2026_user-data-migration-canonical_779286.md` (user migration handoff — prerequisite)
- `30-06-2026_architecture-v15-execution_e02526.md` (architecture v1.5 execution)
- `30-06-2026_business-logic-data-audit_7111e7.md` (business logic audit)

**Key files for this task:**
- `/tmp/migrate_orders.py` (existing MongoDB → PG orders migration)
- `plat/management/commands/migrate_legacy_eshop.py` (eShop orders migration)
- CREATE: `plat/management/commands/migrate_orders_canonical.py` (master orders migration with identity resolution)

**Target DB:** `KungOS_PG_One` (`kuro-cadence`)
**Source DBs:** `KungOS_Mongo_One` (MongoDB), `kg_eshop_latest` (PostgreSQL), `kuropurchase` (MongoDB legacy)

---

## Goal

Audit the current orders migration state, identify gaps between source and target, and design a clean re-migration strategy that:

1. **Maps every order to an identity-based user** via `customer_id` FK → `users_identity.identity_id`
2. **Resolves raw phone numbers** to proper `ESH*`/`ID*` identity IDs
3. **Preserves order lineage** via source `order_id` and collection origin
4. **Handles null customer gracefully** (walk-ins, third-party orders, estimates without identity)

---

## 1. Source → Target Mapping (Current State)

### 1.1 Collection Mapping Overview

| Source Collection | Source DB | Source Count | Target `order_type` | Target Count | Detail Table | Detail Count | Gap |
|---|---|---|---|---|---|---|---|
| `estimates` | KungOS_Mongo_One | 4,308 | `estimate` | 4,308 | `estimate_detail` | 4,308 | **0** ✅ |
| `kgorders` | KungOS_Mongo_One | 9,162 | `in_store` | 9,172 | `in_store_detail` | 9,162 | **+10** ⚠️ |
| `tporders` | KungOS_Mongo_One | 229 | `tp` | 229 | `tp_order_detail` | 229 | **0** ✅ |
| `serviceRequest` | KungOS_Mongo_One | 1,625 | `service` | 1,623 | `service_detail` | 1,623 | **-2** ⚠️ |
| `orders_orders` | kg_eshop_latest | 1,206 | `eshop` | 992 | `eshop_detail` | 993 | **-214** 🔴 |
| (live kiosk) | — | — | `cafe_fnb` | 3 | `cafe_fnb_detail` | 3 | **N/A** |
| **TOTAL** | — | **15,525+** | — | **16,327** | — | **16,318** | **+802** |

### 1.2 Gap Analysis

#### 1.2.1 eShop: 1,206 source → 992 target (−214 missing) 🔴

**Root cause:** eShop source has `delete_flag=true` on 231 records. The migration script filters these out.

```sql
-- Source breakdown
SELECT count(*) as total,
       count(*) FILTER (WHERE delete_flag = true) as deleted,
       count(*) FILTER (WHERE delete_flag = false) as active
FROM orders_orders;
-- total: 1206, deleted: 231, active: 975
```

**Remaining gap:** 975 active − 992 target = **+17 extra in target** (likely from re-runs with `ON CONFLICT DO UPDATE` creating duplicates, or orders migrated via different process).

**Investigation needed:**
- Check if 17 extra target orders have `order_id` not in source
- Verify `eshop_detail` count (993) vs `orders_core` eshop count (992) — **1 orphan detail row**

```sql
-- Find orphan eshop_detail
SELECT d.order_id
FROM eshop_detail d
LEFT JOIN orders_core o ON d.order_id = o.id
WHERE o.id IS NULL;
```

**Recommendation:** During clean re-migration, use `ON CONFLICT (order_id) DO UPDATE` and verify detail table counts match core table counts.

#### 1.2.2 kgorders: 9,162 source → 9,172 target (+10 extra) ⚠️

**Root cause:** 10 extra `in_store` orders in target have non-standard order_id prefixes:
- 9 orders with `channel = 'Online Orders'` (hex order_ids like `673DF4897D`, `CBADFF99D6`)
- 1 order with `FNB` prefix (cafe order misclassified as `in_store`)

```sql
-- Non-KG prefix in_store orders
SELECT order_id, customer_name, channel, total_amount
FROM orders_core
WHERE order_type = 'in_store'
AND order_id NOT LIKE 'KG%';
-- Returns 9 hex + 10 FNB = 19 total
```

**These are NOT from kgorders.** They appear to be:
- **9 hex-prefixed orders:** Created via the web app (not migrated from MongoDB). These are live orders from the current system, not legacy data.
- **10 FNB-prefixed orders:** Cafe/F&B orders that were misclassified as `in_store` (should be `cafe_fnb`).

**Recommendation:** During clean re-migration:
- Exclude orders with `channel = 'Online Orders'` and hex order_ids from legacy migration (they're live system data)
- Reclassify FNB-prefixed orders to `cafe_fnb` type
- Only migrate `kgorders` from `KungOS_Mongo_One` (9,162 records, all with `bg_code`)

#### 1.2.3 serviceRequest: 1,625 source → 1,623 target (−2 missing) ⚠️

**Root cause:** 2 service requests were skipped during migration (likely missing `srid` or duplicate detection).

```javascript
// Source: all have srid
db.serviceRequest.countDocuments({srid: {$ne: ''}})  // 1625
```

**Investigation needed:** Find which 2 `srid` values are missing from target.

```sql
-- Find missing service orders
SELECT sr.srid
FROM (
  SELECT DISTINCT srid FROM KungOS_Mongo_One.serviceRequest
) sr
LEFT JOIN orders_core o ON sr.srid = o.order_id AND o.order_type = 'service'
WHERE o.order_id IS NULL;
```

**Recommendation:** During clean re-migration, log skipped records with reason (missing srid, FK violation, etc.).

#### 1.2.4 kuropurchase kgorders: 12,134 records (not migrated)

**Status:** `kuropurchase.kgorders` has 12,134 records (all with `bg_code: 'KURO0001'`). These were NOT included in the target migration.

**Question:** Are these a superset of `KungOS_Mongo_One.kgorders` (9,162)? Or do they contain additional orders?

```javascript
// Check overlap
// kuropurchase kgorders: 12,134 (all with bg_code)
// KungOS_Mongo_One kgorders: 9,162 (all with bg_code)
// Gap: 2,972 orders in kuropurchase not in KungOS_Mongo_One
```

**Recommendation:** Before re-migration, verify if kuropurchase kgorders contain orders not in KungOS_Mongo_One. If yes, merge into KungOS_Mongo_One first (with dedup by `orderid`).

---

## 2. Target Schema (orders_core + detail tables)

### 2.1 orders_core Schema

```sql
Table "public.orders_core"
 Column            | Type
-------------------+---------------------------
 id                | bigint (PK, auto-increment)
 order_id          | character varying(50) UNIQUE (source order ID)
 order_type        | character varying(20) CHECK (in ('in_store','estimate','service','eshop','tp','cafe_fnb'))
 status            | character varying(20)
 customer_name     | character varying(100)
 customer_phone    | character varying(20)
 customer_email    | character varying(100)
 customer_id       | character varying(20) → FK users_identity(identity_id) [NULLABLE]
 bg_code           | character varying(20)
 div_code          | character varying(50)
 branch_code       | character varying(50)
 total_amount      | numeric(12,2)
 currency          | character varying(3) DEFAULT 'INR'
 channel           | character varying(50)
 bill_address      | jsonb
 products          | jsonb
 active            | boolean DEFAULT true
 delete_flag       | boolean DEFAULT false
 created_by        | character varying(50)
 created_date      | timestamp with time zone
 updated_by        | character varying(50)
 updated_date      | timestamp with time zone

Indexes:
  orders_core_order_id_key (UNIQUE)
  orders_core_customer_id_9867986d_fk_users_identity_identity_id (FK)
```

**Key constraint:** `customer_id` is a **nullable FK** to `users_identity.identity_id`. This allows orders without a resolved identity (walk-ins, third-party orders).

### 2.2 Detail Tables Schema

#### estimate_detail
```sql
 order_id (BIGINT PK) → orders_core(id)
 estimate_number (VARCHAR(50))
 version (INTEGER)
 valid_until (DATE)
 items (JSONB)
```

#### in_store_detail
```sql
 order_id (BIGINT PK) → orders_core(id)
 table_number (VARCHAR(10))
 dine_in (BOOLEAN)
 items (JSONB)
 outward_entries (JSONB)
```

#### tp_order_detail
```sql
 order_id (BIGINT PK) → orders_core(id)
 platform (VARCHAR(50))
 platform_order_id (VARCHAR(100))
 authorized_by (VARCHAR(50))
 authorized_date (TIMESTAMPTZ)
 dispatchby_date (DATE)
 fin_year (VARCHAR(10))
 items (JSONB)
```

#### service_detail
```sql
 order_id (BIGINT PK) → orders_core(id)
 service_type (VARCHAR(50))
 description (TEXT)
 scheduled_date (DATE)
 completed_date (DATE)
```

#### eshop_detail
```sql
 order_id (BIGINT PK) → orders_core(id)
 status (VARCHAR(20))
 payment_method (VARCHAR(20))
 shipping_address (JSONB)
 billing_address (JSONB)
 package_fees (NUMERIC)
 build_fees (NUMERIC)
 shipping_fees (NUMERIC)
 tax_amount (NUMERIC)
 discount_amount (NUMERIC)
 product_total (NUMERIC)
 shipping_agency (VARCHAR(50))
 tracking_number (VARCHAR(100))
 failed_order_id (VARCHAR(50))
 processing_fees (NUMERIC)
 is_custom_build (BOOLEAN)
 assigned_build_id (VARCHAR(50))
 payment_reference (VARCHAR(100))
```

#### cafe_fnb_detail
```sql
 order_id (BIGINT PK) → orders_core(id)
 session_id (BIGINT) → caf_platform_sessions(id) [NULLABLE]
 identity_id (VARCHAR(20)) → users_identity(identity_id) [NOT NULL]
 items (JSONB)
 payment_method (VARCHAR(20)) CHECK (in ('wallet','cash','upi'))
 order_source (VARCHAR(20)) CHECK (in ('kiosk','staff','mobile','web'))
 prepared_at (TIMESTAMPTZ)
 completed_at (TIMESTAMPTZ)
```

**Note:** `cafe_fnb_detail` has its own `identity_id` FK (separate from `orders_core.customer_id`). This is a design inconsistency — consider consolidating.

---

## 3. Customer ID Resolution (The Critical Issue)

### 3.1 Current Distribution

```sql
SELECT
  count(*) as total,
  count(*) FILTER (WHERE customer_id ~ '^ID[0-9]+$') as id_prefix,
  count(*) FILTER (WHERE customer_id ~ '^[0-9]{10}$') as raw_numeric,
  count(*) FILTER (WHERE customer_id ~ '^ESH[0-9]+$') as esh_prefix,
  count(*) FILTER (WHERE customer_id IS NULL OR customer_id = '') as null_empty
FROM orders_core;
```

| Category | Count | Description |
|---|---|---|
| `ID*` prefix | 14,978 | Proper identity IDs (MongoDB walk-ins, estimates, service, TP) |
| Raw 10-digit | 992 | eShop orders with raw phone number as `customer_id` |
| `ESH*` prefix | 0 | **None** — eShop orders NOT mapped to ESH identities |
| NULL/empty | 357 | Orders without customer identity |
| **TOTAL** | **16,327** | |

### 3.2 Why Raw Numeric `customer_id` Works (Currently)

The 992 eShop orders with raw numeric `customer_id` (e.g., `8123300583`) **do satisfy the FK constraint** because:

- There are 2,468 identities with raw numeric `identity_id` in `users_identity`
- These were created by the pre-script migration process (before `migrate_legacy_eshop.py`)
- The FK `orders_core_customer_id_..._fk_users_identity_identity_id` resolves successfully

```sql
-- Verification: all non-null customer_id resolve
SELECT
  count(*) as total,
  count(*) FILTER (WHERE i.identity_id IS NOT NULL) as resolved,
  count(*) FILTER (WHERE i.identity_id IS NULL) as unresolved
FROM orders_core o
LEFT JOIN users_identity i ON o.customer_id = i.identity_id;
-- total: 16327, resolved: 15970, unresolved: 0
```

### 3.3 The Problem

**The raw numeric identity_id is inconsistent with the target design.** The user migration handoff (`779286`) identifies that these 2,468 raw numeric identities should be converted to proper `ESH*` or `ID*` prefix format.

**Impact on orders:**
- If raw numeric identities are converted to `ESH*`/`ID*`, all 992 eShop orders must be updated to reference the new `identity_id`
- If raw numeric identities are deleted and re-created with proper prefix, the FK constraint will break unless orders are updated atomically

### 3.4 Resolution Strategy (Clean Re-migration)

**Prerequisite:** User migration must complete first (Phases 1-5 of user handoff `779286`). All identities must have proper `ESH*`/`ID*` prefix.

**Step 1: Build phone → identity_id lookup**

```python
# After user migration, build lookup:
phone_to_identity = {}
for identity in users_identity:
    normalized_phone = normalize_phone(identity.phone)  # remove spaces, +91 prefix
    phone_to_identity[normalized_phone] = identity.identity_id
```

**Step 2: Resolve customer_id during order migration**

```python
def resolve_customer_id(order_phone, order_type):
    """Resolve customer_id from phone number to identity_id."""
    if not order_phone:
        return None  # walk-in / anonymous order
    
    normalized = normalize_phone(order_phone)
    
    if order_type == 'eshop':
        # Try ESH* identity first
        identity = find_identity_by_phone(normalized, prefix='ESH')
        if identity:
            return identity.identity_id
        # Fall back to raw numeric (pre-script migration)
        identity = find_identity_by_phone(normalized, prefix=None)
        if identity:
            return identity.identity_id
        # Last resort: create new ESH* identity
        return create_eshop_identity(normalized)
    
    elif order_type in ('in_store', 'estimate', 'service'):
        # Try ID* identity first
        identity = find_identity_by_phone(normalized, prefix='ID')
        if identity:
            return identity.identity_id
        # Fall back to any identity
        identity = find_identity_by_phone(normalized)
        if identity:
            return identity.identity_id
        # Walk-in: leave customer_id NULL
        return None
    
    elif order_type == 'tp':
        # TP orders: try any identity, leave NULL if not found
        return find_identity_by_phone(normalized)
    
    return None
```

**Step 3: Null customer_id orders (357 total)**

| Order Type | Count | Resolution |
|---|---|---|
| `tp` | 138 | Leave NULL — third-party orders don't need identity |
| `estimate` | 136 | Leave NULL — quotes without customer identity |
| `in_store` | 82 | Leave NULL — walk-in purchases |
| `service` | 1 | Leave NULL — anonymous service request |

**These are intentionally anonymous.** The FK constraint allows NULL. No action needed.

### 3.5 Phone Normalization

**Source formats:**
- eShop: `095829 44439` (10 digits with space)
- MongoDB: `7517831567` (10 digits, no prefix)
- Target: `+918799708065` (with +91 prefix) or `095829 44439` (as-is from eShop)

**Normalization function:**
```python
def normalize_phone(phone: str) -> str:
    """Normalize phone to 10-digit Indian number."""
    if not phone:
        return ''
    # Remove spaces, dashes, +91 prefix
    cleaned = phone.replace(' ', '').replace('-', '').replace('+', '')
    if cleaned.startswith('91') and len(cleaned) == 12:
        cleaned = cleaned[2:]  # Remove 91 prefix
    if cleaned.startswith('0') and len(cleaned) == 11:
        cleaned = cleaned[1:]  # Remove leading 0
    return cleaned[:10]  # Ensure 10 digits
```

---

## 4. Clean Re-Migration Plan (7 Phases)

**Prerequisite:** Target DB wiped and reset (Phase 0 of user handoff `779286`).
**Dependency:** User migration complete (all identities have proper `ESH*`/`ID*` prefix).

### Phase 1: Pre-Migration Validation

**Goal:** Verify source data integrity before migration.

```python
# Validate source collections
sources = {
    'estimates': ('KungOS_Mongo_One', 'estimates', 'estimate_no'),
    'kgorders': ('KungOS_Mongo_One', 'kgorders', 'orderid'),
    'tporders': ('KungOS_Mongo_One', 'tporders', 'orderid'),
    'serviceRequest': ('KungOS_Mongo_One', 'serviceRequest', 'srid'),
    'eshop_orders': ('kg_eshop_latest', 'orders_orders', 'orderid'),
}

for name, (db, collection, id_field) in sources.items():
    count = get_collection_count(db, collection)
    with_bg_code = get_count_with_field(db, collection, 'bg_code')
    print(f'{name}: {count} total, {with_bg_code} with bg_code')
    
    # Check for duplicate order_ids
    duplicates = find_duplicates(db, collection, id_field)
    if duplicates:
        print(f'  ⚠️ {len(duplicates)} duplicate {id_field} values')
```

**Validation criteria:**
- [ ] All source collections have expected counts
- [ ] All records have `bg_code` (or default to `KURO0001`)
- [ ] No duplicate `order_id` values within each collection
- [ ] Cross-collection `order_id` uniqueness verified (no collisions between sources)

### Phase 2: Phone → Identity Lookup Table

**Goal:** Build a lookup table for phone → identity_id resolution.

```python
# Build lookup from users_identity
cur.execute("""
    SELECT identity_id, phone, name
    FROM users_identity
    WHERE identity_id ~ '^(ID|ESH)[0-9]+$'
""")
phone_to_identity = {}
for identity_id, phone, name in cur.fetchall():
    normalized = normalize_phone(phone)
    if normalized:
        phone_to_identity[normalized] = {
            'identity_id': identity_id,
            'name': name,
            'phone': phone
        }

print(f'Built lookup: {len(phone_to_identity)} phone → identity mappings')
```

**Verification:**
```sql
-- Verify all phones in orders source have matching identity
SELECT count(DISTINCT user.phone) as unique_phones_in_source
FROM KungOS_Mongo_One.kgorders;

-- Compare with identity lookup
SELECT count(*) as identities_with_phone
FROM users_identity
WHERE phone IS NOT NULL AND phone != '';
```

### Phase 3: eShop Orders Migration

**Goal:** Migrate eShop orders with proper `ESH*` identity resolution.

**Source:** `kg_eshop_latest.orders_orders` (1,206 records, 975 active)
**Target:** `orders_core` (order_type='eshop') + `eshop_detail`

**Migration logic:**
```python
def migrate_eshop_orders(source_conn, target_conn, phone_lookup):
    """Migrate eShop orders with identity resolution."""
    cur = source_conn.cursor()
    target_cur = target_conn.cursor()
    
    # Get all active orders
    cur.execute("""
        SELECT orderid, userid, order_status, order_total, channel,
               delete_flag, order_created, order_placed, order_confirmed,
               order_packed, order_shipped, order_delivered,
               pkg_fees, build_fees, shp_fees, tax_total, kuro_discount,
               shp_agency, shp_awb, shp_status, shp_addressid, bill_addressid,
               fail_orderid
        FROM orders_orders
        WHERE delete_flag = false
        ORDER BY orderid
    """)
    
    orders = cur.fetchall()
    print(f'Found {len(orders)} active eShop orders')
    
    migrated = 0
    skipped = 0
    
    for order in orders:
        orderid = order[0]
        userid = order[1]  # raw phone number
        
        # Resolve customer_id from phone
        normalized_phone = normalize_phone(userid)
        identity_info = phone_lookup.get(normalized_phone)
        
        if identity_info:
            customer_id = identity_info['identity_id']
            customer_name = identity_info['name']
            customer_phone = identity_info['phone']
        else:
            # Fallback: use raw data
            customer_id = None  # Will be resolved later
            customer_name = ''
            customer_phone = userid
        
        try:
            # Insert into orders_core
            target_cur.execute("""
                INSERT INTO orders_core (
                    order_id, order_type, status, customer_name, customer_phone,
                    customer_email, bg_code, div_code, branch_code,
                    total_amount, currency, channel, bill_address, products,
                    active, delete_flag, created_by, created_date, updated_by, updated_date,
                    customer_id
                ) VALUES (%s, 'eshop', %s, %s, %s, '', 'KURO0001', 'KURO0001_001', 'KURO0001_001_001',
                          %s, 'INR', %s, '{}', '{}', true, false, %s, NOW(), '', NOW(), %s)
                ON CONFLICT (order_id) DO UPDATE SET status = EXCLUDED.status
                RETURNING id
            """, (
                orderid, order[2][:20], customer_name, customer_phone,
                order[7], order[8], userid, customer_id
            ))
            order_id = target_cur.fetchone()[0]
            
            # Insert into eshop_detail
            target_cur.execute("""
                INSERT INTO eshop_detail (
                    order_id, status, payment_method, shipping_address, billing_address,
                    package_fees, build_fees, shipping_fees, tax_amount, discount_amount,
                    product_total, shipping_agency, tracking_number, failed_order_id
                ) VALUES (%s, %s, 'UPI', '{}', '{}', %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (order_id) DO NOTHING
            """, (
                order_id, order[2][:20],
                order[9] or 0, order[10] or 0, order[11] or 0,
                order[12] or 0, order[13] or 0, order[7],
                order[14] or '', order[15] or '', order[19] or ''
            ))
            
            migrated += 1
            
        except Exception as e:
            print(f'  ERROR migrating order {orderid}: {e}')
            target_conn.rollback()
            skipped += 1
    
    target_conn.commit()
    print(f'eShop orders: {migrated} migrated, {skipped} skipped')
    return migrated
```

**Validation:**
```sql
-- Verify eShop orders
SELECT count(*) as total,
       count(*) FILTER (WHERE customer_id IS NOT NULL) as with_identity,
       count(*) FILTER (WHERE customer_id ~ '^ESH[0-9]+$') as esh_prefix,
       count(*) FILTER (WHERE customer_id ~ '^ID[0-9]+$') as id_prefix,
       count(*) FILTER (WHERE customer_id ~ '^[0-9]+$') as raw_numeric
FROM orders_core
WHERE order_type = 'eshop';
```

**Expected:** All 975 active eShop orders migrated, all with `ESH*` prefix `customer_id`.

### Phase 4: MongoDB Orders Migration (estimates, kgorders, tporders, serviceRequest)

**Goal:** Migrate all MongoDB order collections with identity resolution.

**Source collections:**
- `estimates` → `orders_core` (order_type='estimate') + `estimate_detail`
- `kgorders` → `orders_core` (order_type='in_store') + `in_store_detail`
- `tporders` → `orders_core` (order_type='tp') + `tp_order_detail`
- `serviceRequest` → `orders_core` (order_type='service') + `service_detail`

**Migration logic (generic):**
```python
def migrate_mongo_orders(mongo_db, pg_conn, collection, order_type, id_field, phone_lookup):
    """Generic MongoDB orders migration with identity resolution."""
    col = mongo_db[collection]
    docs = list(col.find())
    print(f'Found {len(docs)} {collection} documents')
    
    cur = pg_conn.cursor()
    
    # Get existing order IDs
    cur.execute("SELECT order_id FROM orders_core")
    existing_orders = {row[0] for row in cur.fetchall()}
    
    migrated = 0
    skipped = 0
    unresolved_customers = 0
    
    for doc in docs:
        order_id = doc.get(id_field)
        if not order_id:
            print(f'  Skipping doc without {id_field}: {doc.get("_id")}')
            skipped += 1
            continue
        
        if order_id in existing_orders:
            skipped += 1
            continue
        
        # Extract customer info
        user = doc.get('user', {})
        customer_name = user.get('name', '')
        customer_phone = user.get('phone', '')
        
        # Resolve customer_id
        normalized_phone = normalize_phone(customer_phone)
        identity_info = phone_lookup.get(normalized_phone)
        
        if identity_info:
            resolved_customer_id = identity_info['identity_id']
            # Update name from identity if source is empty
            if not customer_name and identity_info['name']:
                customer_name = identity_info['name']
        else:
            resolved_customer_id = None
            if customer_phone:
                unresolved_customers += 1
        
        # ... (insert into orders_core + detail table)
        # Same pattern as Phase 3
    
    print(f'{collection}: {migrated} migrated, {skipped} skipped, {unresolved_customers} unresolved')
    return migrated
```

**Collection-specific field mapping:**

| Source | ID Field | Status Field | Total Field | Detail Fields |
|---|---|---|---|---|
| `estimates` | `estimate_no` | `status` | `totalprice` | `validity`, `warranty_terms`, `items` |
| `kgorders` | `orderid` | `order_status` | `totalprice` | `invoice_no`, `invoice_generated`, `po_ref`, `dispatchby_date` |
| `tporders` | `orderid` | `order_status` | `totalprice` | `channel`, `tporderid`, `dispatchby_date`, `fin_year`, `items` |
| `serviceRequest` | `srid` | `status` | `0` (N/A) | `servicetype`, `issue`, `device`, `logs` |

**Validation:**
```sql
-- Verify all MongoDB orders
SELECT order_type, count(*) as total,
       count(*) FILTER (WHERE customer_id IS NOT NULL) as with_identity,
       count(*) FILTER (WHERE customer_id ~ '^ID[0-9]+$') as id_prefix,
       count(*) FILTER (WHERE customer_id IS NULL) as null_customer
FROM orders_core
WHERE order_type IN ('estimate', 'in_store', 'tp', 'service')
GROUP BY order_type
ORDER BY order_type;
```

### Phase 5: Cross-Validation

**Goal:** Verify migration completeness and data integrity.

```python
def validate_migration(pg_conn):
    """Validate orders migration completeness."""
    cur = pg_conn.cursor()
    
    # 1. Count validation
    cur.execute("""
        SELECT order_type, count(*) as total
        FROM orders_core
        GROUP BY order_type
        ORDER BY order_type
    """)
    print('Order counts:')
    for row in cur.fetchall():
        print(f'  {row[0]}: {row[1]}')
    
    # 2. FK validation (all non-null customer_id must resolve)
    cur.execute("""
        SELECT count(*) as unresolved
        FROM orders_core o
        LEFT JOIN users_identity i ON o.customer_id = i.identity_id
        WHERE o.customer_id IS NOT NULL AND i.identity_id IS NULL
    """)
    unresolved = cur.fetchone()[0]
    print(f'\nUnresolved customer_id: {unresolved}')
    assert unresolved == 0, 'FK constraint violation!'
    
    # 3. Detail table validation (all orders must have detail)
    cur.execute("""
        SELECT 'estimate' as type, count(*) as gap
        FROM orders_core o
        LEFT JOIN estimate_detail d ON o.id = d.order_id
        WHERE o.order_type = 'estimate' AND d.order_id IS NULL
        UNION ALL
        SELECT 'in_store', count(*)
        FROM orders_core o
        LEFT JOIN in_store_detail d ON o.id = d.order_id
        WHERE o.order_type = 'in_store' AND d.order_id IS NULL
        UNION ALL
        SELECT 'tp', count(*)
        FROM orders_core o
        LEFT JOIN tp_order_detail d ON o.id = d.order_id
        WHERE o.order_type = 'tp' AND d.order_id IS NULL
        UNION ALL
        SELECT 'service', count(*)
        FROM orders_core o
        LEFT JOIN service_detail d ON o.id = d.order_id
        WHERE o.order_type = 'service' AND d.order_id IS NULL
        UNION ALL
        SELECT 'eshop', count(*)
        FROM orders_core o
        LEFT JOIN eshop_detail d ON o.id = d.order_id
        WHERE o.order_type = 'eshop' AND d.order_id IS NULL
    """)
    print('\nMissing detail rows:')
    for row in cur.fetchall():
        if row[1] > 0:
            print(f'  {row[0]}: {row[1]} missing')
    
    # 4. Orphan detail rows
    cur.execute("""
        SELECT 'estimate' as type, count(*) as orphan
        FROM estimate_detail d
        LEFT JOIN orders_core o ON d.order_id = o.id
        WHERE o.id IS NULL
        UNION ALL
        SELECT 'in_store', count(*)
        FROM in_store_detail d
        LEFT JOIN orders_core o ON d.order_id = o.id
        WHERE o.id IS NULL
        -- ... (repeat for other types)
    """)
    print('\nOrphan detail rows:')
    for row in cur.fetchall():
        if row[1] > 0:
            print(f'  {row[0]}: {row[1]} orphan')
    
    cur.close()
    print('\n✅ Validation complete')
```

### Phase 6: kuropurchase kgorders Merge (if needed)

**Goal:** If kuropurchase contains orders not in KungOS_Mongo_One, merge them.

```python
def merge_kuropurchase_orders(kuropurchase_db, kungos_db, pg_conn, phone_lookup):
    """Merge kuropurchase kgorders into KungOS_Mongo_One and migrate."""
    # Get order IDs already in KungOS_Mongo_One
    kungos_order_ids = set(doc['orderid'] for doc in kungos_db.kgorders.find({}, {'orderid': 1}))
    
    # Find orders in kuropurchase not in KungOS_Mongo_One
    missing = []
    for doc in kuropurchase_db.kgorders.find():
        if doc.get('orderid') not in kungos_order_ids:
            missing.append(doc)
    
    print(f'Found {len(missing)} kuropurchase orders not in KungOS_Mongo_One')
    
    if missing:
        # Insert into KungOS_Mongo_One (with lineage tracking)
        for doc in missing:
            doc['migrated_from'] = 'kuropurchase'
            doc['migrated_at'] = datetime.now().isoformat()
            kungos_db.kgorders.insert_one(doc)
        
        # Then migrate as normal (Phase 4)
        migrate_mongo_orders(kungos_db, pg_conn, 'kgorders', 'in_store', 'orderid', phone_lookup)
```

**Pre-condition:** Verify kuropurchase kgorders overlap with KungOS_Mongo_One kgorders before executing.

### Phase 7: Production Validation

**Goal:** Final validation before marking migration complete.

```sql
-- 1. Total order count
SELECT count(*) as total_orders FROM orders_core;

-- 2. Order type distribution
SELECT order_type, count(*) as cnt
FROM orders_core
GROUP BY order_type
ORDER BY cnt DESC;

-- 3. Customer ID resolution
SELECT
  count(*) as total,
  count(*) FILTER (WHERE customer_id ~ '^ID[0-9]+$') as id_prefix,
  count(*) FILTER (WHERE customer_id ~ '^ESH[0-9]+$') as esh_prefix,
  count(*) FILTER (WHERE customer_id ~ '^[0-9]+$') as raw_numeric,
  count(*) FILTER (WHERE customer_id IS NULL) as null_customer
FROM orders_core;

-- 4. FK integrity
SELECT count(*) as fk_violations
FROM orders_core o
LEFT JOIN users_identity i ON o.customer_id = i.identity_id
WHERE o.customer_id IS NOT NULL AND i.identity_id IS NULL;

-- 5. Detail table completeness
SELECT 
  'estimate' as type,
  (SELECT count(*) FROM orders_core WHERE order_type = 'estimate') as core,
  (SELECT count(*) FROM estimate_detail) as detail
UNION ALL
SELECT 'in_store',
  (SELECT count(*) FROM orders_core WHERE order_type = 'in_store'),
  (SELECT count(*) FROM in_store_detail)
UNION ALL
SELECT 'tp',
  (SELECT count(*) FROM orders_core WHERE order_type = 'tp'),
  (SELECT count(*) FROM tp_order_detail)
UNION ALL
SELECT 'service',
  (SELECT count(*) FROM orders_core WHERE order_type = 'service'),
  (SELECT count(*) FROM service_detail)
UNION ALL
SELECT 'eshop',
  (SELECT count(*) FROM orders_core WHERE order_type = 'eshop'),
  (SELECT count(*) FROM eshop_detail)
UNION ALL
SELECT 'cafe_fnb',
  (SELECT count(*) FROM orders_core WHERE order_type = 'cafe_fnb'),
  (SELECT count(*) FROM cafe_fnb_detail);

-- 6. Top customers by order count
SELECT i.identity_id, i.name, i.phone, count(*) as order_count
FROM orders_core o
JOIN users_identity i ON o.customer_id = i.identity_id
GROUP BY i.identity_id, i.name, i.phone
ORDER BY order_count DESC
LIMIT 10;
```

---

## 5. Implementation Units

### Unit 1: Create `migrate_orders_canonical.py`

**Location:** `plat/management/commands/migrate_orders_canonical.py`

**Dependencies:**
- User migration complete (all identities have proper prefix)
- Target DB schema exists (orders_core + detail tables)

**Features:**
- Phone → identity lookup table
- Collection-specific migration functions
- Cross-validation after each collection
- Error logging with retry capability

**Acceptance criteria:**
- [ ] All 6 order types migrated with correct counts
- [ ] All non-null `customer_id` resolve to `users_identity`
- [ ] No orphan detail rows
- [ ] No missing detail rows
- [ ] Source order_id preserved in target

### Unit 2: Update `migrate_legacy_eshop.py` (optional)

**Goal:** Fix eShop orders migration to use proper `ESH*` identity resolution.

**Changes:**
- Replace raw `userid` with resolved `customer_id` from identity lookup
- Add phone normalization
- Handle `delete_flag=true` orders explicitly (skip with log)

**Acceptance criteria:**
- [ ] All active eShop orders have `ESH*` prefix `customer_id`
- [ ] Detail table count matches core table count
- [ ] No raw numeric `customer_id` in eShop orders

### Unit 3: Validation Script

**Location:** `plat/management/commands/validate_orders_migration.py`

**Features:**
- Source → target count comparison
- FK integrity check
- Detail table completeness check
- Orphan detection
- Customer ID resolution audit

**Acceptance criteria:**
- [ ] Zero FK violations
- [ ] Zero orphan detail rows
- [ ] Zero missing detail rows
- [ ] All expected order types present

---

## 6. Risk Assessment

| Risk | Severity | Mitigation |
|---|---|---|
| Raw numeric identity_id conversion breaks FK | HIGH | Atomic transaction: update identity_id + update all orders in same TX |
| Phone normalization mismatch | MEDIUM | Test normalization against all source phone formats before migration |
| Duplicate order_id across collections | LOW | Verify cross-collection uniqueness pre-migration |
| kuropurchase orders not in KungOS_Mongo_One | MEDIUM | Investigate before re-migration; merge if needed |
| eShop order items not migrated | LOW | Verify `orders_orderitems` (1,350) are included in `products` JSONB |
| Service request logs lost | LOW | Ensure `logs` array migrated to `service_detail` |

---

## 7. Open Questions

1. **kuropurchase kgorders (12,134) vs KungOS_Mongo_One kgorders (9,162):** Are kuropurchase orders a superset? Need to verify overlap before deciding whether to merge.

2. **eShop order items (1,350 in `orders_orderitems`):** Are these included in the `products` JSONB field during migration? Need to verify.

3. **10 FNB-prefixed orders in `in_store`:** Should these be reclassified to `cafe_fnb`? Or are they legitimate in_store orders with FNB prefix?

4. **2 missing service requests:** Which `srid` values were skipped? Need to investigate root cause.

5. **17 extra eShop orders in target:** Where did these come from? Need to trace source.

6. **`tpbuilds` (123 records):** Should these be migrated separately? They represent TP build configurations, not orders.

7. **`outward` collection (754/781):** Purpose unknown — may contain order-related outward entries.

---

## 8. Execution Order

1. **Complete user migration first** (Phases 1-5 of `779286`)
2. **Verify all identities have proper prefix** (`ESH*` or `ID*`)
3. **Execute Phase 1:** Pre-migration validation
4. **Execute Phase 2:** Build phone → identity lookup
5. **Execute Phase 3:** eShop orders migration
6. **Execute Phase 4:** MongoDB orders migration
7. **Execute Phase 5:** Cross-validation
8. **Execute Phase 6:** kuropurchase merge (if needed)
9. **Execute Phase 7:** Production validation

---

## Appendix A: Source Data Samples

### A.1 estimates (KungOS_Mongo_One)
```json
{
  "_id": "643d47244473b9382072fbdc",
  "estimate_no": "KGE-210000110",
  "status": "quoted",
  "user": { "name": "K Venkat Ram", "phone": "7207435848" },
  "billadd": { "name": "K Venkat Ram", "phone": "7207435848", "city": "Hyderabad", "state": "Telangana" },
  "totalprice": 52208,
  "builds": [...],
  "products": [...],
  "bg_code": "KURO0001",
  "div_code": "KURO0001_001",
  "branch_code": "KURO0001_001_001"
}
```

### A.2 kgorders (KungOS_Mongo_One)
```json
{
  "_id": "663220db0c7135126b77816f",
  "orderid": "KG23000004",
  "order_status": "Delivered",
  "invoice_no": "KG-100002",
  "invoice_generated": true,
  "user": { "name": "Roshan Samuel", "phone": "7517831567" },
  "billadd": { "company": "Royal Public School", "name": "Roshan Samuel", "phone": "7517831567", "city": "Bhandara" },
  "totalprice": 179550,
  "builds": [...],
  "bg_code": "KURO0001",
  "div_code": "KURO0001_001",
  "branch_code": "KURO0001_001_001"
}
```

### A.3 tporders (KungOS_Mongo_One)
```json
{
  "_id": "668a574209a99aaa33fde350",
  "orderid": "TP20cb402cd538",
  "order_status": "Delivered",
  "channel": "Amazon",
  "tporderid": "404-2273353-3613919",
  "user": { "name": "Akash Kumar", "phone": "", "email": "" },
  "shpadd": { "name": "Akash Kumar", "city": "PUNE", "state": "Maharashtra" },
  "totalprice": 10120,
  "products": [...],
  "bg_code": "KURO0001",
  "div_code": "KURO0001_001",
  "branch_code": "KURO0001_001_001"
}
```

### A.4 serviceRequest (KungOS_Mongo_One)
```json
{
  "_id": "670a3db12649df38c382af78",
  "srid": "KSR0000D",
  "status": "resolved",
  "servicetype": "Third Party Warranty Service",
  "name": "Ashik",
  "phone": "7305400842",
  "device": "Third Party Warranty Service",
  "issue": "SMPS Replacement",
  "logs": [...],
  "bg_code": "KURO0001",
  "div_code": "KURO0001_001",
  "branch_code": "KURO0001_001_001"
}
```

### A.5 orders_orders (kg_eshop_latest)
```sql
-- Sample row
orderid: '6569ac1f42'
userid: '8123300583'
order_status: 'Payment Pending'
order_total: 1288.00
delete_flag: false
channel: 'online'
```

---

## Appendix B: Migration Script Template

```python
#!/usr/bin/env python3
"""
Canonical Orders Migration — All Sources → KungOS_PG_One

Prerequisites:
- User migration complete (all identities have ESH*/ID* prefix)
- Target DB schema exists (orders_core + detail tables)

Usage:
  python manage.py migrate_orders_canonical --source-db KungOS_Mongo_One
  python manage.py migrate_orders_canonical --source-db kg_eshop_latest
  python manage.py migrate_orders_canonical --all
"""
import os
import sys
import json
from datetime import datetime

import pymongo
import psycopg2
from psycopg2.extras import execute_values

# Phone normalization
def normalize_phone(phone):
    """Normalize phone to 10-digit Indian number."""
    if not phone:
        return ''
    cleaned = str(phone).replace(' ', '').replace('-', '').replace('+', '')
    if cleaned.startswith('91') and len(cleaned) == 12:
        cleaned = cleaned[2:]
    if cleaned.startswith('0') and len(cleaned) == 11:
        cleaned = cleaned[1:]
    return cleaned[:10]

# Build phone → identity lookup
def build_phone_lookup(pg_conn):
    """Build phone → identity_id lookup from users_identity."""
    cur = pg_conn.cursor()
    cur.execute("""
        SELECT identity_id, phone, name
        FROM users_identity
        WHERE identity_id ~ '^(ID|ESH)[0-9]+$'
          AND phone IS NOT NULL AND phone != ''
    """)
    lookup = {}
    for identity_id, phone, name in cur.fetchall():
        normalized = normalize_phone(phone)
        if normalized:
            lookup[normalized] = {
                'identity_id': identity_id,
                'name': name,
                'phone': phone
            }
    cur.close()
    return lookup

# Resolve customer_id
def resolve_customer_id(phone, order_type, phone_lookup):
    """Resolve customer_id from phone to identity_id."""
    if not phone:
        return None
    normalized = normalize_phone(phone)
    return phone_lookup.get(normalized, {}).get('identity_id')

# Migration functions (one per collection)
# ... (see Phase 3-4 for detailed implementations)

def main():
    """Main migration entry point."""
    # Connect to sources
    mongo_client = pymongo.MongoClient('mongodb://127.0.0.1:27017/')
    mongo_db = mongo_client['KungOS_Mongo_One']
    
    eshop_conn = psycopg2.connect(
        dbname='kg_eshop_latest', user='postgres', host='/var/run/postgresql'
    )
    
    pg_conn = psycopg2.connect(
        dbname='kuro-cadence', user='postgres', host='/var/run/postgresql'
    )
    
    try:
        # Build lookup
        phone_lookup = build_phone_lookup(pg_conn)
        print(f'Built phone lookup: {len(phone_lookup)} entries')
        
        # Migrate collections
        migrate_eshop_orders(eshop_conn, pg_conn, phone_lookup)
        migrate_mongo_orders(mongo_db, pg_conn, 'estimates', 'estimate', 'estimate_no', phone_lookup)
        migrate_mongo_orders(mongo_db, pg_conn, 'kgorders', 'in_store', 'orderid', phone_lookup)
        migrate_mongo_orders(mongo_db, pg_conn, 'tporders', 'tp', 'orderid', phone_lookup)
        migrate_mongo_orders(mongo_db, pg_conn, 'serviceRequest', 'service', 'srid', phone_lookup)
        
        # Validate
        validate_migration(pg_conn)
        
    finally:
        eshop_conn.close()
        pg_conn.close()
        mongo_client.close()

if __name__ == '__main__':
    main()
```

---

## Appendix C: Related Documents

| Document | Purpose |
|---|---|
| `30-06-2026_user-data-migration-canonical_779286.md` | User migration handoff (prerequisite) |
| `30-06-2026_architecture-v15-execution_e02526.md` | Architecture v1.5 execution plan |
| `30-06-2026_business-logic-data-audit_7111e7.md` | Business logic data audit |
| `/tmp/migrate_orders.py` | Existing orders migration script (reference) |
| `plat/management/commands/migrate_legacy_eshop.py` | eShop migration script (reference) |
