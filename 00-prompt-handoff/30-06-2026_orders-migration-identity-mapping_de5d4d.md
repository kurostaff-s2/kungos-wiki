# Orders Migration & Identity Mapping Audit (CORRECTED)

| Field | Value |
|-------|-------|
| Project ID | `kteam-dj-chief` |
| Primary entity ID | `de5d4d-v2` |
| Entity type | `handoff` |
| Short description | Corrected audit of orders migration from TRUE legacy sources (kuropurchase + kg_eshop_latest) to `KungOS_PG_One` with proper tenant mapping and identity resolution |
| Status | `draft` |
| Source references | `30-06-2026_user-data-migration-canonical_779286.md`, `30-06-2026_architecture-v15-execution_e02526.md` |
| Generated | `30-06-2026` |
| Next action / owner | Execute orders re-migration after user migration (Phase 8-9 in user handoff) |

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Reference docs:**
- `30-06-2026_user-data-migration-canonical_779286.md` (user migration handoff — prerequisite)
- `30-06-2026_architecture-v15-execution_e02526.md` (architecture v1.5 execution)
- `30-06-2026_business-logic-data-audit_7111e7.md` (business logic data audit)

**Target DB:** `KungOS_PG_One` (`kuro-cadence`)
**TRUE Legacy Source DBs:**
- `kuropurchase` (MongoDB) — legacy, NO tenant fields
- `kg_eshop_latest` (PostgreSQL) — legacy, NO tenant fields

**NOT a source:** `KungOS_Mongo_One` is a pre-migrated/canonicalized version of kuropurchase (subset with tenant fields). Use only for reference, NOT as source.

---

## Goal

Audit the current orders migration state from TRUE legacy sources, identify all gaps, and design a clean re-migration strategy that:

1. **Maps every order to an identity-based user** via `customer_id` FK → `users_identity.identity_id`
2. **Enriches tenant fields** (bg_code, div_code, branch_code) for all kuropurchase records
3. **Resolves raw phone numbers** to proper `ESH*`/`ID*` identity IDs
4. **Preserves order lineage** via source `order_id` and collection origin
5. **Handles null customer gracefully** (walk-ins, third-party orders, estimates without identity)

---

## 1. Source → Target Mapping (CORRECTED: TRUE Legacy Counts)

### 1.1 Collection Mapping Overview

| Source Collection | Source DB | Legacy Count | Target `order_type` | Target Count | Detail Table | Detail Count | Gap (Legacy → Target) |
|---|---|---|---|---|---|---|---|
| `kgorders` | kuropurchase | 12,134 | `in_store` | 9,172 | `in_store_detail` | 9,162 | **−2,962** 🔴 |
| `estimates` | kuropurchase | 5,052 | `estimate` | 4,308 | `estimate_detail` | 4,308 | **−744** 🔴 |
| `tporders` | kuropurchase | 229 | `tp` | 229 | `tp_order_detail` | 229 | **0** ✅ |
| `serviceRequest` | kuropurchase | 1,627 | `service` | 1,623 | `service_detail` | 1,623 | **−4** ⚠️ |
| `orders_orders` | kg_eshop_latest | 1,206 (975 active) | `eshop` | 992 | `eshop_detail` | 993 | **+17** 🔴 |
| (live kiosk) | — | — | `cafe_fnb` | 3 | `cafe_fnb_detail` | 12 | **N/A** |
| **TOTAL** | — | **19,248** | — | **16,327** | — | **16,318** | **−2,921** |

### 1.2 Critical Finding: KungOS_Mongo_One is a FILTERED SUBSET

The previous handoff used `KungOS_Mongo_One` counts which were already filtered. The TRUE gaps are:

| Collection | kuropurchase | KungOS_Mongo_One | Target | Missing (kuropurchase → KungOS) | Missing (KungOS → Target) |
|---|---|---|---|---|---|
| `kgorders` | 12,134 | 9,162 | 9,172 | **2,972** | +10 (web app) |
| `estimates` | 5,052 | 4,308 | 4,308 | **744** | 0 |
| `tporders` | 229 | 229 | 229 | 0 | 0 |
| `serviceRequest` | 1,627 | 1,625 | 1,623 | **2** | −2 |

**KungOS_Mongo_One is a strict subset of kuropurchase** (0 records exist in KungOS that aren't in kuropurchase). The records missing from KungOS were excluded during the initial consolidation (likely due to missing tenant fields or data quality issues).

### 1.3 Gap Analysis

#### 1.3.1 kgorders: 12,134 legacy → 9,172 target (−2,962 missing) 🔴

**Root cause:** 2,972 `kgorders` exist in `kuropurchase` but were NOT migrated to `KungOS_Mongo_One` (and therefore not to target). The +10 in target are web app orders (hex order_ids, `channel = 'Online Orders'`).

**Investigation:**
```javascript
// kuropurchase kgorders NOT in KungOS_Mongo_One
// 2,972 records — need to inspect why they were excluded
db.kgorders.find({orderid: {$nin: kungosOrderIds}}).limit(5).forEach(doc => printjson(doc));
```

**Recommendation:** During clean re-migration:
1. Enrich ALL 12,134 kuropurchase kgorders with tenant fields
2. Migrate directly from kuropurchase (bypass KungOS_Mongo_One)
3. Exclude web app orders (hex order_ids, `channel = 'Online Orders'`) from legacy migration
4. Reclassify FNB-prefixed orders to `cafe_fnb` type

#### 1.3.2 estimates: 5,052 legacy → 4,308 target (−744 missing) 🔴

**Root cause:** 744 `estimates` exist in `kuropurchase` but were NOT migrated to `KungOS_Mongo_One`.

**Investigation:**
```javascript
// kuropurchase estimates NOT in KungOS_Mongo_One
// 744 records — need to inspect why they were excluded
db.estimates.find({estimate_no: {$nin: kungosEstimateNos}}).limit(5).forEach(doc => printjson(doc));
```

**Recommendation:** During clean re-migration:
1. Enrich ALL 5,052 kuropurchase estimates with tenant fields
2. Migrate directly from kuropurchase

#### 1.3.3 serviceRequest: 1,627 legacy → 1,623 target (−4 missing) ⚠️

**Root cause:** 2 service requests missing from KungOS_Mongo_One, plus 2 more missing from target.

**Investigation:**
```javascript
// kuropurchase serviceRequest NOT in KungOS_Mongo_One
// 2 records
db.serviceRequest.find({srid: {$nin: kungosSrids}}).forEach(doc => printjson(doc));
```

**Recommendation:** During clean re-migration, log skipped records with reason.

#### 1.3.4 eShop: 1,206 legacy (975 active) → 992 target 🔴

**Root cause:** Complex migration error with two components:

1. **172 deleted orders migrated** (should have been skipped): Orders with `delete_flag=true` were migrated before the filter was applied consistently. All 172 have `order_status = 'Payment Method Changed'`.

2. **155 active orders missing** (should have been migrated): Orders with `delete_flag=false` were NOT migrated. All have `order_status = 'Payment Pending'`.

```
Source: 1,206 total (975 active, 231 deleted)
Target: 992 total
  - 820 common (correctly migrated active orders)
  - 172 extra (migrated from deleted source — should be removed)
  - 155 missing (active orders not migrated — should be migrated)
```

**Recommendation:** During clean re-migration:
1. Filter `delete_flag = false` strictly
2. Migrate ALL 975 active orders
3. Remove 172 deleted orders from target
4. Include `orders_orderitems` (1,350 items across 1,198 orders) in `products` JSONB

#### 1.3.5 FNB Order Misclassification 🔴

**10 FNB-prefixed orders** are in `orders_core` as `in_store` type but should be `cafe_fnb`:
- 9 have detail rows in `cafe_fnb_detail` (data inconsistency)
- 1 (FNB20260628122055) has NO detail row anywhere
- All have empty customer fields (name, phone, customer_id)
- All have small amounts (₹90-100) — typical F&B orders

**Impact:**
- `in_store_detail`: 9,162 vs 9,172 in_store core (10 missing = FNB orders)
- `cafe_fnb_detail`: 12 vs 3 cafe_fnb core (9 extra = FNB orders with wrong type)

**Recommendation:** During clean re-migration:
1. Reclassify FNB-prefixed orders to `cafe_fnb` type
2. Ensure detail rows match core type
3. Handle the 1 FNB order without detail row (skip or create minimal detail)

---

## 2. Tenant Mapping (Critical Gap)

### 2.1 kuropurchase: ZERO Tenant Fields

**ALL kuropurchase collections have NO `bg_code`, `div_code`, or `branch_code`:**

| Collection | Count | bg_code | div_code | branch_code |
|---|---|---|---|---|
| `kgorders` | 12,134 | 0 | 0 | 0 |
| `estimates` | 5,052 | 0 | 0 | 0 |
| `tporders` | 229 | 0 | 0 | 0 |
| `serviceRequest` | 1,627 | 0 | 0 | 0 |
| `tpbuilds` | 123 | 0 | 0 | 0 |
| `outward` | 781 | 0 | 0 | 0 |
| `purchaseorders` | 5,555 | 0 | 0 | 0 |

### 2.2 kg_eshop_latest: NO Tenant Fields

`orders_orders` schema has NO `bg_code`, `div_code`, or `branch_code` columns.

### 2.3 Target: Partial Tenant Coverage

| Order Type | Total | With bg_code | With div_code | With branch_code | Empty div/branch |
|---|---|---|---|---|---|
| `in_store` | 9,172 | 9,172 | 9,162 | 9,162 | 10 (FNB + web app) |
| `estimate` | 4,308 | 4,308 | 4,308 | 4,308 | 0 |
| `service` | 1,623 | 4,308 | 4,308 | 4,308 | 0 |
| `eshop` | 992 | 992 | 992 | 992 | 0 |
| `tp` | 229 | 229 | 229 | 229 | 0 |
| `cafe_fnb` | 3 | 3 | 2 | 2 | 1 |

### 2.4 Tenant Enrichment Strategy

**For clean re-migration, apply default tenant fields to ALL legacy records:**

```python
DEFAULT_TENANT = {
    'bg_code': 'KURO0001',
    'div_code': 'KURO0001_001',
    'branch_code': 'KURO0001_001_001'
}
```

**Caveat:** If multi-tenant data is discovered (e.g., `entity` field in kuropurchase indicates different tenants), adjust accordingly. Current evidence suggests single-tenant (`kurogaming` / `KURO0001`).

```javascript
// Check for multi-tenant indicators
db.kgorders.distinct('entity');  // Returns: ['kurogaming'] (all same)
```

---

## 3. Target Schema (orders_core + detail tables)

### 3.1 orders_core Schema

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

### 3.2 Detail Tables Schema

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

### 3.3 FK Constraints

| Constraint | Table | Column | References |
|---|---|---|---|
| `orders_core_customer_id_...` | `orders_core` | `customer_id` | `users_identity(identity_id)` |
| `*_detail_order_id_...` | All detail tables | `order_id` | `orders_core(id)` |
| `cafe_fnb_detail_identity_id_...` | `cafe_fnb_detail` | `identity_id` | `users_identity(identity_id)` |
| `cafe_fnb_detail_session_id_...` | `cafe_fnb_detail` | `session_id` | `caf_platform_sessions(id)` |

---

## 4. Customer ID Resolution (The Critical Issue)

### 4.1 Current Distribution

| Order Type | Total | With Customer | `ID*` prefix | `ESH*` prefix | Raw Numeric | NULL |
|---|---|---|---|---|---|---|
| `in_store` | 9,172 | 9,090 | 9,090 | 0 | 0 | 82 |
| `estimate` | 4,308 | 4,172 | 4,172 | 0 | 0 | 136 |
| `service` | 1,623 | 1,622 | 1,622 | 0 | 0 | 1 |
| `eshop` | 992 | 992 | 0 | 0 | 992 | 0 |
| `tp` | 229 | 91 | 91 | 0 | 0 | 138 |
| `cafe_fnb` | 3 | 3 | 3 | 0 | 0 | 0 |

**Key issue:** All 992 eShop orders have **raw numeric `customer_id`** (10-digit phone) instead of `ESH*` prefix. This works because 2,468 raw numeric identities exist in `users_identity`, but it's inconsistent with the target design.

### 4.2 eShop Phone Format (Critical for Normalization)

**ALL 3,378 eShop user phones have format:** `"0" + 5 digits + space + 5 digits` (12 chars total)

Examples:
- `087298 26164` → normalize to `8729826164`
- `095112 20403` → normalize to `9511220403`

**Normalization function:**
```python
def normalize_phone(phone: str) -> str:
    """Normalize phone to 10-digit Indian number."""
    if not phone:
        return ''
    # Remove spaces, dashes, +91 prefix
    cleaned = str(phone).replace(' ', '').replace('-', '').replace('+', '')
    if cleaned.startswith('91') and len(cleaned) == 12:
        cleaned = cleaned[2:]  # Remove 91 prefix
    if cleaned.startswith('0') and len(cleaned) == 11:
        cleaned = cleaned[1:]  # Remove leading 0
    # eShop special case: "0" + 5 digits + 5 digits = 11 chars after space removal
    if cleaned.startswith('0') and len(cleaned) == 11:
        cleaned = cleaned[1:]  # Remove leading 0
    return cleaned[:10]  # Ensure 10 digits
```

### 4.3 Resolution Strategy (Clean Re-migration)

**Prerequisite:** User migration must complete first (Phases 1-5 of user handoff `779286`). All identities must have proper `ESH*`/`ID*` prefix.

**Step 1: Build phone → identity_id lookup**

```python
# After user migration, build lookup:
phone_to_identity = {}
for identity in users_identity:
    normalized_phone = normalize_phone(identity.phone)
    if normalized_phone:
        phone_to_identity[normalized_phone] = identity.identity_id
```

**Step 2: Resolve customer_id during order migration**

```python
def resolve_customer_id(order_phone, order_type, phone_lookup):
    """Resolve customer_id from phone number to identity_id."""
    if not order_phone:
        return None  # walk-in / anonymous order

    normalized = normalize_phone(order_phone)

    if order_type == 'eshop':
        # Try ESH* identity first
        identity = find_identity_by_phone(normalized, prefix='ESH')
        if identity:
            return identity.identity_id
        # Fall back to any identity
        identity = find_identity_by_phone(normalized)
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

---

## 5. Data Quality Issues

### 5.1 eShop Order Items

| Metric | Value |
|---|---|
| Total items | 1,350 |
| Orders with items | 1,198 |
| Orders without items | 8 |
| Unique products | 444 |
| Min quantity | −1 (data error) |
| Max quantity | 10 |

**8 orders without items:**
- 7 are `Payment Pending` (abandoned carts)
- 1 is `Payment Method Changed` with `delete_flag=true`

**1 item with negative quantity:** Needs investigation (likely a return/adjustment).

### 5.2 eShop Address Data

| Table | Count | With User |
|---|---|---|
| `accounts_addresslist` | 1,064 | 1,064 |
| `accounts_cart` | 748 | 748 |
| `accounts_wishlist` | 450 | 450 |

**Recommendation:** Migrate `accounts_addresslist` to `eshop_detail.shipping_address` / `billing_address` via `shp_addressid` / `bill_addressid` FK.

### 5.3 FNB Order Misclassification (Detailed)

| Order ID | Current Type | Correct Type | Detail Location | Amount |
|---|---|---|---|---|
| FNB20260628122055 | `in_store` | `cafe_fnb` | NONE (missing) | ₹100 |
| FNB20260628123155 | `in_store` | `cafe_fnb` | `cafe_fnb_detail` | ₹100 |
| FNB20260628123205 | `in_store` | `cafe_fnb` | `cafe_fnb_detail` | ₹90 |
| FNB20260628123807 | `in_store` | `cafe_fnb` | `cafe_fnb_detail` | ₹90 |
| FNB20260628123954 | `in_store` | `cafe_fnb` | `cafe_fnb_detail` | ₹90 |
| FNB20260628132143 | `in_store` | `cafe_fnb` | `cafe_fnb_detail` | ₹90 |
| FNB20260628132149 | `in_store` | `cafe_fnb` | `cafe_fnb_detail` | ₹90 |
| FNB20260628132650 | `in_store` | `cafe_fnb` | `cafe_fnb_detail` | ₹90 |
| FNB20260628132811 | `in_store` | `cafe_fnb` | `cafe_fnb_detail` | ₹90 |
| FNB20260628133001 | `in_store` | `cafe_fnb` | `cafe_fnb_detail` | ₹90 |

### 5.4 Web App Orders (Not Legacy)

9 orders with hex `order_id` and `channel = 'Online Orders'` are live system data, NOT legacy data. They should be excluded from legacy migration:

| Order ID | Customer | Amount | Channel |
|---|---|---|---|
| 673DF4897D | Arhaan Khurana | ₹130,876 | (empty) |
| CBADFF99D6 | Adithya A | ₹45,465 | (empty) |
| F03BB0ADAE | Vineet Suneja | ₹78,003 | (empty) |
| d23d337c1f | Dinesh V Raut | ₹146,574 | Online Orders |
| 28f3fc5e82 | Priyatam Singh | ₹98,822 | Online Orders |
| d2d777f326 | Reza Tholalu | ₹115,018 | Online Orders |
| 2a215246d6 | ONGC | ₹115,503 | Online Orders |
| ce3b400abc | Unmesh Moosad | ₹44,528 | Online Orders |
| ceeb0f6919 | VIVEK KUMAR SINHA | ₹1,427 | Online Orders |

---

## 6. Clean Re-Migration Plan (8 Phases)

**Prerequisite:** Target DB wiped and reset (Phase 0 of user handoff `779286`).
**Dependency:** User migration complete (all identities have proper `ESH*`/`ID*` prefix).

### Phase 0: Source Data Enrichment (kuropurchase)

**Goal:** Add tenant fields to ALL kuropurchase order collections.

```python
def enrich_kuropurchase_tenant_fields(mongo_client):
    """Add default tenant fields to kuropurchase collections."""
    db = mongo_client['kuropurchase']
    default_tenant = {
        'bg_code': 'KURO0001',
        'div_code': 'KURO0001_001',
        'branch_code': 'KURO0001_001_001'
    }

    collections = ['kgorders', 'estimates', 'tporders', 'serviceRequest']
    for col_name in collections:
        col = db[col_name]
        result = col.update_many(
            {'bg_code': {'$exists': False}},
            {'$set': default_tenant}
        )
        print(f'{col_name}: {result.modified_count} records enriched')
```

**Validation:**
```javascript
// Verify all records have tenant fields
db.kgorders.countDocuments({bg_code: 'KURO0001'})  // Should be 12,134
db.estimates.countDocuments({bg_code: 'KURO0001'})  // Should be 5,052
```

### Phase 1: Pre-Migration Validation

**Goal:** Verify source data integrity before migration.

```python
# Validate source collections
sources = {
    'kgorders': ('kuropurchase', 'kgorders', 'orderid'),
    'estimates': ('kuropurchase', 'estimates', 'estimate_no'),
    'tporders': ('kuropurchase', 'tporders', 'orderid'),
    'serviceRequest': ('kuropurchase', 'serviceRequest', 'srid'),
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
- [ ] All records have `bg_code` (after enrichment)
- [ ] No duplicate `order_id` values within each collection
- [ ] Cross-collection `order_id` uniqueness verified

### Phase 2: Phone → Identity Lookup Table

**Goal:** Build a lookup table for phone → identity_id resolution.

```python
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

    # Get all ACTIVE orders only
    cur.execute("""
        SELECT orderid, userid, order_status, order_total, channel,
               delete_flag, order_created, order_placed, order_confirmed,
               order_packed, order_shipped, order_delivered,
               pkg_fees, build_fees, shp_fees, tax_total, kuro_discount,
               shp_agency, shp_awb, shp_status, shp_addressid, bill_addressid,
               fail_orderid, payment_option, upi_address, pay_reference
        FROM orders_orders
        WHERE delete_flag = false
        ORDER BY orderid
    """)

    orders = cur.fetchall()
    print(f'Found {len(orders)} active eShop orders')

    # Load address data
    cur.execute("SELECT addressid, fullname, phone, addressline1, addressline2, city, state, pincode FROM accounts_addresslist WHERE delete_flag = false")
    addresses = {row[0]: row for row in cur.fetchall()}

    # Load order items
    cur.execute("SELECT orderid, productid, title, price, quantity, hsn_code, tax_cgst, tax_sgst, tax_igst, components FROM orders_orderitems")
    items_by_order = {}
    for row in cur.fetchall():
        oid = row[0]
        if oid not in items_by_order:
            items_by_order[oid] = []
        items_by_order[oid].append({
            'productid': row[1], 'title': row[2], 'price': row[3],
            'quantity': row[4], 'hsn_code': row[5],
            'tax_cgst': row[6], 'tax_sgst': row[7], 'tax_igst': row[8],
            'components': row[9]
        })

    migrated = 0
    skipped = 0

    for order in orders:
        orderid = order[0]
        userid = order[1]  # raw phone number (format: "0XXXXX XXXXX")

        # Resolve customer_id from phone
        normalized_phone = normalize_phone(userid)
        identity_info = phone_lookup.get(normalized_phone)

        if identity_info:
            customer_id = identity_info['identity_id']
            customer_name = identity_info['name']
            customer_phone = identity_info['phone']
        else:
            customer_id = None
            customer_name = ''
            customer_phone = userid

        # Build products JSONB from order items
        products_json = json.dumps(items_by_order.get(orderid, []))

        # Build shipping/billing address JSONB
        shp_addr = addresses.get(order[20], {})  # shp_addressid
        bill_addr = addresses.get(order[21], {})  # bill_addressid

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
                          %s, 'INR', %s, %s, %s, true, false, %s, NOW(), '', NOW(), %s)
                ON CONFLICT (order_id) DO UPDATE SET status = EXCLUDED.status
                RETURNING id
            """, (
                orderid, order[2][:20], customer_name, customer_phone,
                order[3] or 0, order[4],
                json.dumps(bill_addr) if bill_addr else '{}',
                products_json, userid, customer_id
            ))
            core_id = target_cur.fetchone()[0]

            # Insert into eshop_detail
            target_cur.execute("""
                INSERT INTO eshop_detail (
                    order_id, status, payment_method, shipping_address, billing_address,
                    package_fees, build_fees, shipping_fees, tax_amount, discount_amount,
                    product_total, shipping_agency, tracking_number, failed_order_id,
                    payment_reference
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (order_id) DO NOTHING
            """, (
                core_id, order[2][:20],
                order[23] or 'UPI',  # payment_option
                json.dumps(shp_addr) if shp_addr else '{}',
                json.dumps(bill_addr) if bill_addr else '{}',
                order[12] or 0, order[13] or 0, order[14] or 0,
                order[15] or 0, order[16] or 0, order[3] or 0,
                order[17] or '', order[18] or '', order[22] or '',
                order[25] or ''  # pay_reference
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
       count(*) FILTER (WHERE customer_id ~ '^ESH[0-9]+$') as esh_prefix
FROM orders_core
WHERE order_type = 'eshop';
```

**Expected:** 975 active eShop orders migrated, all with `ESH*` prefix `customer_id`.

### Phase 4: MongoDB Orders Migration (estimates, kgorders, tporders, serviceRequest)

**Goal:** Migrate all MongoDB order collections with identity resolution.

**Source collections (from kuropurchase directly):**
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
            skipped += 1
            continue

        if order_id in existing_orders:
            skipped += 1
            continue

        # Extract customer info (varies by collection)
        if collection == 'serviceRequest':
            customer_name = doc.get('name', '')
            customer_phone = doc.get('phone', '')
        else:
            user = doc.get('user', {})
            customer_name = user.get('name', '')
            customer_phone = user.get('phone', '')

        # Resolve customer_id
        normalized_phone = normalize_phone(customer_phone)
        identity_info = phone_lookup.get(normalized_phone)

        if identity_info:
            resolved_customer_id = identity_info['identity_id']
            if not customer_name and identity_info['name']:
                customer_name = identity_info['name']
        else:
            resolved_customer_id = None
            if customer_phone:
                unresolved_customers += 1

        # Extract tenant fields (enriched in Phase 0)
        bg_code = doc.get('bg_code', 'KURO0001')
        div_code = doc.get('div_code', 'KURO0001_001')
        branch_code = doc.get('branch_code', 'KURO0001_001_001')

        # ... (insert into orders_core + detail table)
        # Collection-specific field mapping below

    print(f'{collection}: {migrated} migrated, {skipped} skipped, {unresolved_customers} unresolved')
    return migrated
```

**Collection-specific field mapping:**

| Source | ID Field | Status Field | Total Field | Phone Field | Detail Fields |
|---|---|---|---|---|---|
| `estimates` | `estimate_no` | `status` | `totalprice` | `user.phone` | `validity`, `warranty_terms`, `items` |
| `kgorders` | `orderid` | `order_status` | `totalprice` | `user.phone` | `invoice_no`, `invoice_generated`, `po_ref`, `dispatchby_date` |
| `tporders` | `orderid` | `order_status` | `totalprice` | `user.phone` | `channel`, `tporderid`, `dispatchby_date`, `fin_year`, `items` |
| `serviceRequest` | `srid` | `status` | `0` (N/A) | `phone` (direct) | `servicetype`, `issue`, `device`, `logs` |

**FNB order handling:**
```python
# During kgorders migration, check for FNB prefix
if order_id.startswith('FNB'):
    order_type = 'cafe_fnb'  # Reclassify
    # Insert into cafe_fnb_detail instead of in_store_detail
```

**Web app order exclusion:**
```python
# Exclude web app orders (hex order_ids, channel = 'Online Orders')
if order_id not in kuro_order_ids and doc.get('channel') == 'Online Orders':
    skipped += 1
    continue
```

### Phase 5: Cross-Validation

**Goal:** Verify migration completeness and data integrity.

```python
def validate_migration(pg_conn):
    """Validate orders migration completeness."""
    cur = pg_conn.cursor()

    # 1. Count validation
    expected = {
        'in_store': 12134,  # All kuropurchase kgorders (minus web app)
        'estimate': 5052,   # All kuropurchase estimates
        'tp': 229,          # All kuropurchase tporders
        'service': 1627,    # All kuropurchase serviceRequest
        'eshop': 975,       # Active eShop orders only
        'cafe_fnb': 3,      # Live kiosk (not from legacy)
    }

    cur.execute("""
        SELECT order_type, count(*) as total
        FROM orders_core
        GROUP BY order_type
        ORDER BY order_type
    """)
    actual = {row[0]: row[1] for row in cur.fetchall()}

    print('Order counts:')
    for order_type, exp_count in expected.items():
        act_count = actual.get(order_type, 0)
        status = '✅' if act_count == exp_count else '🔴'
        print(f'  {status} {order_type}: expected={exp_count}, actual={act_count}')

    # 2. FK validation
    cur.execute("""
        SELECT count(*) as unresolved
        FROM orders_core o
        LEFT JOIN users_identity i ON o.customer_id = i.identity_id
        WHERE o.customer_id IS NOT NULL AND i.identity_id IS NULL
    """)
    unresolved = cur.fetchone()[0]
    print(f'\nUnresolved customer_id: {unresolved}')
    assert unresolved == 0, 'FK constraint violation!'

    # 3. Detail table validation
    detail_tables = {
        'estimate': 'estimate_detail',
        'in_store': 'in_store_detail',
        'tp': 'tp_order_detail',
        'service': 'service_detail',
        'eshop': 'eshop_detail',
        'cafe_fnb': 'cafe_fnb_detail',
    }

    print('\nDetail table completeness:')
    for order_type, detail_table in detail_tables.items():
        cur.execute(f"""
            SELECT count(*) as missing
            FROM orders_core o
            LEFT JOIN {detail_table} d ON o.id = d.order_id
            WHERE o.order_type = %s AND d.order_id IS NULL
        """, (order_type,))
        missing = cur.fetchone()[0]
        status = '✅' if missing == 0 else '🔴'
        print(f'  {status} {order_type}: {missing} missing detail rows')

    # 4. Orphan detail rows
    print('\nOrphan detail rows:')
    for order_type, detail_table in detail_tables.items():
        cur.execute(f"""
            SELECT count(*) as orphan
            FROM {detail_table} d
            LEFT JOIN orders_core o ON d.order_id = o.id
            WHERE o.id IS NULL
        """)
        orphan = cur.fetchone()[0]
        status = '✅' if orphan == 0 else '🔴'
        print(f'  {status} {detail_table}: {orphan} orphan rows')

    cur.close()
    print('\n✅ Validation complete')
```

### Phase 6: Production Validation

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
  order_type,
  count(*) as core_count,
  CASE order_type
    WHEN 'estimate' THEN (SELECT count(*) FROM estimate_detail)
    WHEN 'in_store' THEN (SELECT count(*) FROM in_store_detail)
    WHEN 'tp' THEN (SELECT count(*) FROM tp_order_detail)
    WHEN 'service' THEN (SELECT count(*) FROM service_detail)
    WHEN 'eshop' THEN (SELECT count(*) FROM eshop_detail)
    WHEN 'cafe_fnb' THEN (SELECT count(*) FROM cafe_fnb_detail)
  END as detail_count
FROM orders_core
GROUP BY order_type;

-- 6. Tenant field coverage
SELECT
  bg_code,
  count(*) as total,
  count(*) FILTER (WHERE div_code = '' OR div_code IS NULL) as empty_div,
  count(*) FILTER (WHERE branch_code = '' OR branch_code IS NULL) as empty_branch
FROM orders_core
GROUP BY bg_code;
```

### Phase 7: Cleanup & Lineage Tracking

**Goal:** Ensure all migrated records retain source lineage.

```sql
-- Add lineage tracking columns (if not already present)
ALTER TABLE orders_core ADD COLUMN IF NOT EXISTS source_db VARCHAR(50);
ALTER TABLE orders_core ADD COLUMN IF NOT EXISTS source_collection VARCHAR(100);
ALTER TABLE orders_core ADD COLUMN IF NOT EXISTS migrated_at TIMESTAMPTZ DEFAULT NOW();

-- Update lineage
UPDATE orders_core SET source_db = 'kuropurchase', source_collection = 'kgorders'
WHERE order_type = 'in_store' AND order_id LIKE 'KG%';

UPDATE orders_core SET source_db = 'kuropurchase', source_collection = 'estimates'
WHERE order_type = 'estimate';

UPDATE orders_core SET source_db = 'kuropurchase', source_collection = 'tporders'
WHERE order_type = 'tp';

UPDATE orders_core SET source_db = 'kuropurchase', source_collection = 'serviceRequest'
WHERE order_type = 'service';

UPDATE orders_core SET source_db = 'kg_eshop_latest', source_collection = 'orders_orders'
WHERE order_type = 'eshop';
```

---

## 7. Implementation Units

### Unit 1: Create `migrate_orders_canonical.py`

**Location:** `plat/management/commands/migrate_orders_canonical.py`

**Dependencies:**
- User migration complete (all identities have proper prefix)
- Target DB schema exists (orders_core + detail tables)
- kuropurchase tenant fields enriched (Phase 0)

**Features:**
- Phase 0: Tenant field enrichment for kuropurchase
- Phone → identity lookup table
- Collection-specific migration functions
- eShop order items and address integration
- FNB order reclassification
- Web app order exclusion
- Cross-validation after each collection
- Error logging with retry capability
- Lineage tracking

**Acceptance criteria:**
- [ ] All kuropurchase kgorders migrated (12,134 minus web app)
- [ ] All kuropurchase estimates migrated (5,052)
- [ ] All kuropurchase tporders migrated (229)
- [ ] All kuropurchase serviceRequest migrated (1,627)
- [ ] All active eShop orders migrated (975)
- [ ] No deleted eShop orders migrated
- [ ] All non-null `customer_id` resolve to `users_identity` with proper prefix
- [ ] No orphan detail rows
- [ ] No missing detail rows
- [ ] Source order_id preserved in target
- [ ] Tenant fields populated for all records
- [ ] FNB orders reclassified to `cafe_fnb`
- [ ] eShop order items included in `products` JSONB
- [ ] eShop addresses mapped to detail tables

### Unit 2: Validation Script

**Location:** `plat/management/commands/validate_orders_migration.py`

**Features:**
- Source → target count comparison (TRUE legacy counts)
- FK integrity check
- Detail table completeness check
- Orphan detection
- Customer ID resolution audit
- Tenant field coverage audit
- Lineage tracking verification

**Acceptance criteria:**
- [ ] Zero FK violations
- [ ] Zero orphan detail rows
- [ ] Zero missing detail rows
- [ ] All expected order types present with correct counts
- [ ] All records have tenant fields
- [ ] All eShop orders have `ESH*` prefix `customer_id`

---

## 8. Risk Assessment

| Risk | Severity | Mitigation |
|---|---|---|
| kuropurchase tenant enrichment modifies source data | HIGH | Run enrichment in a separate collection or use `$setOnInsert` with upsert to new collection |
| Phone normalization mismatch (eShop format) | HIGH | Test normalization against ALL 3,378 eShop phone formats before migration |
| eShop order items not migrated | MEDIUM | Include `orders_orderitems` in migration (1,350 items) |
| FNB order reclassification breaks existing data | MEDIUM | Handle during clean re-migration (target wipe first) |
| Deleted eShop orders already in target | MEDIUM | Remove before re-migration or use `ON CONFLICT DO UPDATE` |
| 155 active eShop orders missing | HIGH | Ensure `delete_flag = false` filter is strict |
| 2,972 kgorders missing from KungOS | HIGH | Migrate directly from kuropurchase (bypass KungOS) |
| 744 estimates missing from KungOS | HIGH | Migrate directly from kuropurchase (bypass KungOS) |

---

## 9. Open Questions

1. **2,972 kuropurchase kgorders not in KungOS:** Why were these excluded? Need to inspect data quality before migration.

2. **744 kuropurchase estimates not in KungOS:** Why were these excluded? Need to inspect data quality before migration.

3. **2 kuropurchase serviceRequest not in KungOS:** Which `srid` values were excluded?

4. **eShop order items (1,350):** Should these be migrated as `products` JSONB or as separate detail rows?

5. **eShop addresses (1,064):** Should these be mapped to `eshop_detail` shipping/billing address?

6. **1 item with negative quantity:** Is this a return/adjustment? Should it be excluded or handled specially?

7. **8 eShop orders without items:** Should these be migrated (they represent abandoned carts)?

8. **`tpbuilds` (123 records):** Should these be migrated separately? They represent TP build configurations, not orders.

9. **`outward` collection (781 records):** Purpose unknown — may contain order-related outward entries.

10. **`indentpos` (283) + `indentproduct` (1,649):** These are purchase indent requests, not customer orders. Should they be in a separate migration?

---

## 10. Execution Order

1. **Complete user migration first** (Phases 1-5 of `779286`)
2. **Verify all identities have proper prefix** (`ESH*` or `ID*`)
3. **Execute Phase 0:** Enrich kuropurchase tenant fields
4. **Execute Phase 1:** Pre-migration validation
5. **Execute Phase 2:** Build phone → identity lookup
6. **Execute Phase 3:** eShop orders migration (975 active only)
7. **Execute Phase 4:** MongoDB orders migration (from kuropurchase directly)
8. **Execute Phase 5:** Cross-validation
9. **Execute Phase 6:** Production validation
10. **Execute Phase 7:** Cleanup & lineage tracking

---

## Appendix A: Source Data Samples

### A.1 kgorders (kuropurchase — NO tenant fields)
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
  "bg_code": undefined,
  "div_code": undefined,
  "branch_code": undefined,
  "entity": "kurogaming"
}
```

### A.2 estimates (kuropurchase — NO tenant fields, NO status)
```json
{
  "_id": "643d47244473b9382072fbdc",
  "estimate_no": "KGE-210000110",
  "status": null,
  "user": { "name": "K Venkat Ram", "phone": "7207435848" },
  "billadd": { "name": "K Venkat Ram", "phone": "7207435848", "city": "Hyderabad", "state": "Telangana" },
  "totalprice": 52208,
  "builds": [...],
  "bg_code": undefined,
  "div_code": undefined,
  "branch_code": undefined
}
```

### A.3 tporders (kuropurchase — NO tenant fields)
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
  "bg_code": undefined,
  "div_code": undefined,
  "branch_code": undefined
}
```

### A.4 serviceRequest (kuropurchase — NO tenant fields, direct phone)
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
  "bg_code": undefined,
  "div_code": undefined,
  "branch_code": undefined
}
```

### A.5 orders_orders (kg_eshop_latest — NO tenant fields)
```sql
-- Sample row
orderid: '6569ac1f42'
userid: '8123300583'
order_status: 'Payment Pending'
order_total: 1288.00
delete_flag: false
channel: 'online'
-- NO bg_code, div_code, branch_code columns
```

### A.6 orders_orderitems (kg_eshop_latest)
```sql
-- Sample row
orderid: '6569ac1f42'
productid: 'PROD001'
title: 'Product Name'
price: 1288.00
quantity: 1
hsn_code: '84713000'
tax_cgst: 103.84
tax_sgst: 103.84
tax_igst: 0.00
components: '{"custom": true}'
```

---

## Appendix B: Migration Script Template

```python
#!/usr/bin/env python3
"""
Canonical Orders Migration — ALL Legacy Sources → KungOS_PG_One

Sources:
- kuropurchase (MongoDB): kgorders, estimates, tporders, serviceRequest
- kg_eshop_latest (PostgreSQL): orders_orders, orders_orderitems, accounts_addresslist

Prerequisites:
- User migration complete (all identities have ESH*/ID* prefix)
- Target DB schema exists (orders_core + detail tables)
- kuropurchase tenant fields enriched (Phase 0)

Usage:
  python manage.py migrate_orders_canonical --phase 0  # Enrich tenant fields
  python manage.py migrate_orders_canonical --phase 3  # eShop orders
  python manage.py migrate_orders_canonical --phase 4  # MongoDB orders
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

# Enrich kuropurchase tenant fields
def enrich_kuropurchase_tenant_fields(mongo_client):
    """Add default tenant fields to kuropurchase collections."""
    db = mongo_client['kuropurchase']
    default_tenant = {
        'bg_code': 'KURO0001',
        'div_code': 'KURO0001_001',
        'branch_code': 'KURO0001_001_001'
    }
    collections = ['kgorders', 'estimates', 'tporders', 'serviceRequest']
    for col_name in collections:
        col = db[col_name]
        result = col.update_many(
            {'bg_code': {'$exists': False}},
            {'$set': default_tenant}
        )
        print(f'{col_name}: {result.modified_count} records enriched')

# Migration functions (one per collection)
# ... (see Phase 3-4 for detailed implementations)

def main():
    """Main migration entry point."""
    # Connect to sources
    mongo_client = pymongo.MongoClient('mongodb://127.0.0.1:27017/')
    kuropurchase_db = mongo_client['kuropurchase']

    eshop_conn = psycopg2.connect(
        dbname='kg_eshop_latest', user='postgres', host='/var/run/postgresql'
    )

    pg_conn = psycopg2.connect(
        dbname='kuro-cadence', user='postgres', host='/var/run/postgresql'
    )

    try:
        # Phase 0: Enrich tenant fields
        enrich_kuropurchase_tenant_fields(mongo_client)

        # Phase 2: Build lookup
        phone_lookup = build_phone_lookup(pg_conn)
        print(f'Built phone lookup: {len(phone_lookup)} entries')

        # Phase 3: eShop orders
        migrate_eshop_orders(eshop_conn, pg_conn, phone_lookup)

        # Phase 4: MongoDB orders
        migrate_mongo_orders(kuropurchase_db, pg_conn, 'estimates', 'estimate', 'estimate_no', phone_lookup)
        migrate_mongo_orders(kuropurchase_db, pg_conn, 'kgorders', 'in_store', 'orderid', phone_lookup)
        migrate_mongo_orders(kuropurchase_db, pg_conn, 'tporders', 'tp', 'orderid', phone_lookup)
        migrate_mongo_orders(kuropurchase_db, pg_conn, 'serviceRequest', 'service', 'srid', phone_lookup)

        # Phase 5: Validate
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

---

## Appendix D: Audit Evidence Summary

| Finding | Source | Evidence |
|---|---|---|
| kuropurchase has NO tenant fields | kuropurchase MongoDB | All 4 order collections: 0 records with bg_code/div_code/branch_code |
| kgorders gap: 12,134 → 9,172 | kuropurchase vs target | 2,972 in kuropurchase only (verified via orderid comparison) |
| estimates gap: 5,052 → 4,308 | kuropurchase vs target | 744 in kuropurchase only (verified via estimate_no comparison) |
| serviceRequest gap: 1,627 → 1,623 | kuropurchase vs target | 2 in kuropurchase only + 2 missing from target |
| eShop: 172 deleted migrated | kg_eshop_latest vs target | All 172 have `delete_flag=true` and `order_status='Payment Method Changed'` |
| eShop: 155 active missing | kg_eshop_latest vs target | All 155 have `delete_flag=false` and `order_status='Payment Pending'` |
| eShop phone format: "0XXXXX XXXXX" | kg_eshop_latest | All 3,378 users have 12-char format with space |
| FNB misclassification | kuro-cadence | 10 FNB orders in `in_store`, 9 detail rows in `cafe_fnb_detail` |
| Web app orders (9) | kuro-cadence | Hex order_ids, `channel='Online Orders'`, not in any legacy source |
| eShop items: 1 negative qty | kg_eshop_latest | `orders_orderitems` has 1 row with `quantity = -1` |
| eShop orders without items: 8 | kg_eshop_latest | 7 `Payment Pending` + 1 `Payment Method Changed` (deleted) |
