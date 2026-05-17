# MongoDB Report — KungOS_Mongo_One vs kuropurchase (Legacy)

**Date:** 2026-05-14
**Purpose:** Audit MongoDB state across legacy (`kuropurchase`) and unified (`KungOS_Mongo_One`) databases. Identify schema gaps, data loss, collection mismatches, and cafe-fnb integration blockers.
**Sources:** Live MongoDB 8 introspection, legacy code scan (`kteam-dj-be-main`), `kungos_v2_db.md`, `KungOS_Analytics_Design.md`

---

## Executive Summary

| Metric | kuropurchase (legacy) | KungOS_Mongo_One (unified) | Status |
|--------|----------------------|---------------------------|--------|
| **Collections** | 31 | 31 (+1: `entities`) | ✅ Same count |
| **Total documents** | 47,055 | 68,443 | ⚠️ +21,388 (46% growth) |
| **Tenant fields** | Partial (pre-migration) | 100% (`bgcode`, `division`, `branch_code`) | ✅ Complete |
| **Compound indexes** | Unknown | 31/31 `(bgcode, division)` | ✅ Complete |
| **Collection naming** | camelCase (8 collections) | lowercase (all 31) | ✅ Migrated |
| **F&B menu data** | In `misc` (same) | In `misc` (43 items) | ⚠️ Not in `stock_register` |
| **F&B orders** | Embedded in `kgorders.food[]` | Embedded in `kgorders.food[]` | ⚠️ Not separate collection |
| **Gaming collections** | 12/13 missing | 12/13 missing | ❌ Deferred |

---

## 1. Collection Inventory & Document Counts

### 1.1 Side-by-Side Comparison

| Collection | kuropurchase | KungOS_Mongo_One | Diff | Status |
|------------|-------------|------------------|------|--------|
| `accounts` | 7 | 7 | 0 | ✅ |
| `bgData` | 1 | 1 | 0 | ✅ |
| `employee_attendance` | 966 | 966 | 0 | ✅ |
| `estimates` | 4,850 | 4,308 | -542 | ⚠️ |
| `indentpos` | 250 | 247 | -3 | ⚠️ |
| `indentproduct` | 1,529 | 1,490 | -39 | ⚠️ |
| `inwardinvoices` | **4,626** | **16** | **-4,610** | 🔴 **CRITICAL** |
| `inwardpayments` | 9,467 | 21,026 | +11,559 | ⚠️ |
| `kgorders` | 9,466 | 9,162 | -304 | ⚠️ |
| `misc` | **8** | **5,512** | **+5,504** | ⚠️ |
| `outward` | 756 | 754 | -2 | ⚠️ |
| `outwardinvoices` | 1,167 | 1,165 | -2 | ⚠️ |
| `paymentvouchers` | 3,509 | 3,459 | -50 | ⚠️ |
| `players` | 117 | 117 | 0 | ✅ |
| `presets` | 6 | 6 | 0 | ✅ |
| `products` | 82 | 82 | 0 | ✅ |
| `purchaseorders` | 5,395 | 15,216 | +9,821 | ⚠️ |
| `reb_users` | 2,028 | 1,982 | -46 | ⚠️ |
| `serviceRequest` | 1,625 | 1,625 | 0 | ✅ |
| `stock_register` | 194 | 194 | 0 | ✅ |
| `teams` | 14 | 14 | 0 | ✅ |
| `tournaments` | 3 | 3 | 0 | ✅ |
| `tourneyregister` | 56 | 56 | 0 | ✅ |
| `tpbuilds` | 123 | 123 | 0 | ✅ |
| `tporders` | 229 | 229 | 0 | ✅ |
| `vendors` | 415 | 409 | -6 | ⚠️ |
| **NEW: `entities`** | — | 2 | +2 | ℹ️ |
| **REMOVED: `tempproducts`** | 0 | — | 0 | ℹ️ |

### 1.2 Collections Renamed (camelCase → lowercase)

| Legacy Name | New Name | Docs | 
|------------|----------|------|
| `inwardCreditNotes` | `inwardcreditnotes` | 106 |
| `inwardDebitNotes` | `inwarddebitnotes` | 3 |
| `inwardInvoices` | `inwardinvoices` | 16 (⚠️ was 4,626) |
| `outwardCreditNotes` | `outwardcreditnotes` | 150 |
| `outwardDebitNotes` | `outwarddebitnotes` | 13 |
| `outwardInvoices` | `outwardinvoices` | 1,165 |
| `paymentVouchers` | `paymentvouchers` | 3,459 |

**Legacy code still references camelCase names** — 7 collections affected. Any code path using `db['inwardInvoices']` will fail against `KungOS_Mongo_One`.

### 1.3 Collections Referenced in Code but NOT in Any Database

| Collection | Referenced in | Docs in kuropurchase | Docs in KungOS_Mongo_One |
|------------|--------------|---------------------|-------------------------|
| `gamerDetails` | `rebellion/views.py:264` | 0 | 0 |
| `gamers` | `rebellion/views.py:274-442` | 0 | 0 |
| `rbpackages` | `rebellion/views.py:283` | 0 | 0 |
| `kurodata` | Legacy code | 0 | 0 |
| `media` | Legacy code | 0 | 0 |
| `stock_audit` | Legacy code | 0 | 0 |
| `asset_register` | `KungOS_Analytics_Design.md` | 0 | 0 |

**These are dead references.** The collections were never created or were dropped. Code paths hitting them will error.

---

## 2. Tenant Field Coverage

### 2.1 Status: 31/31 Collections ✅

All collections have `bgcode`, `division`, `branch_code` fields on 100% of documents.

### 2.2 Compound Index Coverage: 31/31 ✅

All collections have `(bgcode, division)` compound indexes.

### 2.3 Division Distribution

| Division (div_code) | Brand | Documents | % |
|---------------------|-------|-----------|---|
| `KURO0001_001` | kurogaming | 61,187 | 89.4% |
| `KURO0001_002` | rebellion | 7,256 | 10.6% |
| `KURO0001_003` | renderedge | 0 | 0% |
| `DUNE0003_001` | rebellion (Dune) | 0 | 0% |
| **Total** | — | **68,443** | 100% |

**Per-collection breakdown (significant splits only):**

| Collection | KURO0001_001 | KURO0001_002 | Notes |
|------------|-------------|-------------|-------|
| `inwardpayments` | 19,980 | 1,046 | 95%/5% split |
| `misc` | 1,752 | 3,760 | 32%/68% split |
| `outward` | 545 | 209 | 72%/28% split |
| `players` | 0 | 117 | 100% rebellion |
| `products` | 0 | 82 | 100% rebellion |
| `reb_users` | 0 | 1,982 | 100% rebellion |
| `tournaments` | 0 | 3 | 100% rebellion |
| `tourneyregister` | 0 | 56 | 100% rebellion |

**Caveat:** `DUNE0003_001` has 0 documents despite being defined in PostgreSQL tenant tables. The legacy migration (`restore_kuropurchase.py`) may not have split rebellion data into the Dune division.

---

## 3. Data Integrity Issues

### 3.1 🔴 CRITICAL: `inwardinvoices` Data Loss

| | kuropurchase | KungOS_Mongo_One |
|--|-------------|------------------|
| **Documents** | 4,626 | 16 |
| **Loss** | — | **4,610 (99.7%)** |

The `inwardinvoices` collection went from 4,626 documents to 16. This is the primary purchase invoice collection — used by `domains.accounts` ViewSets, analytics reports (P&L, Balance Sheet), and the integration plan's Phase 5 migration.

**Impact:**
- `domains.accounts.viewsets.py` queries `inwardinvoices` — will return near-empty results
- All financial analytics depending on inward invoices are broken
- The integration plan notes this: "16 inwardinvoices from 2022-2023" vs "4,626 in production dump"

**Root cause (likely):** The `restore_kuropurchase.py` migration may have only loaded a subset or the collection was renamed without full data transfer.

### 3.2 ⚠️ `purchaseorders` Inflation: 5,395 → 15,216

Growth of 9,821 documents (182%). Two theories:
1. Production dump had more data than legacy DB
2. Data was merged from another collection (e.g., `indentpos` + `indentproduct`)

**Needs verification:** Are the extra 9,821 documents legitimate or duplicates?

### 3.3 ⚠️ `inwardpayments` Inflation: 9,467 → 21,026

Growth of 11,559 documents (122%). Same question as above.

### 3.4 ⚠️ `misc` Collection Bloat: 8 → 5,512

The `misc` collection grew 689x. It's now a catch-all containing:

| Category | Documents | Description |
|----------|-----------|-------------|
| Service requests (empty `type`) | 1,922 | Same schema as `serviceRequest` — duplicates? |
| F&B stock items | 43 | Cafe menu with inventory tracking |
| PC components | ~100 | cpu, gpu, ram, mob, ssd, monitor, etc. |
| Gaming gear | ~58 | controller, ps5, vr, streaming-gear, etc. |
| Accounting entries | ~135 | Expenses, Fixed Assets, Trading Stock |
| System metadata | 11 | counters, brands, states, hsncodes, etc. |

### 3.5 ⚠️ `entity` Field Missing in `kgorders`

The legacy `kgorders` in `kuropurchase` has an `entity` field (brand identifier: `kurogaming`, `rebellion`). In `KungOS_Mongo_One`, this field is **absent** — replaced by `division`/`branch_code`. The legacy analytics code (`order_totals()`) filters by `entity` — this will fail.

---

## 4. `kgorders` Collection — Deep Dive

### 4.1 Schema (100 docs sampled)

| Field | Present in | Type | Notes |
|-------|-----------|------|-------|
| `orderid` | 100% | string | e.g., `KG23000465` |
| `builds[]` | 100% | array | PC build configurations (components) |
| `products[]` | 100% | array | Product line items |
| `totalprice` | 100% | number | Order total |
| `totalpricebgst` | 100% | number | Total excluding GST |
| `gst` | 100% | number | GST amount |
| `taxes` | 100% | object | `{5: 0, 12: 0, 18: X, 28: 0}` |
| `estimate_no` | 100% | string | Reference estimate |
| `invoice_no` | 100% | string | Invoice number |
| `invoice_generated` | 100% | boolean | Has invoice been generated |
| `order_status` | 100% | string | `Delivered`, `Cancelled`, `Shipped`, `Inventory Added`, `None` |
| `order_date` | 100% | ISO string | Order date |
| `user` | 100% | object | `{name, phone}` |
| `billadd` | 100% | object | Billing address |
| `bgcode` | 100% | string | Tenant filter |
| `division` | 100% | string | Tenant filter |
| `branch_code` | 100% | string | Tenant filter |
| `services[]` | 80% | array | Service line items |
| `build_srno[]` | 34% | array | Serial numbers |
| `food[]` | ~93%* | array | **F&B add-on items** |
| `service[]` | ~93%* | array | Service add-on items |

*Based on kuropurchase counts (8,861/9,466 in legacy, 8,561/9,162 in KungOS)

### 4.2 F&B Orders: Embedded, Not Separate

Food orders are **not a separate collection**. They are embedded arrays inside `kgorders`:

```json
{
  "orderid": "KG23000483",
  "food": [
    {"type": "food", "productid": "", "foodtype": "Potato Wedges", "unit": 0, "title": "", "quantity": 1, "price": 250, "totalprice": 0},
    {"type": "beverage", "productid": "TINCOC2510000007", "foodtype": "Tin", "unit": 0, "title": "", "quantity": 1, "price": 60, "totalprice": 0}
  ],
  "service": [
    {"type": "pc144hz", "presetid": "PREHAP0010", "quantity": 1, "price": 449, "totalprice": 0}
  ]
}
```

**Key fields in `food[]` items:**
- `type`: `"food"` or `"beverage"`
- `productid`: Links to `misc` collection (F&B item) — often empty
- `foodtype`: Descriptive name (e.g., "Potato Wedges", "Tin")
- `quantity`: Number of units
- `price`: Per-unit price

**No `session_id` field exists** in `kgorders`. The cafe-fnb gateway's assumption of `session_id` linking is wrong.

### 4.3 What the Cafe-FNB Gateway Assumes vs Reality

| Gateway Field | Exists in kgorders? | Actual Field |
|--------------|-------------------|--------------|
| `items[]` | ❌ | `food[]` + `service[]` + `builds[]` |
| `total` | ❌ | `totalprice` |
| `amount_paid` | ❌ | Not tracked separately |
| `payment_status` | ❌ | `order_status` (different semantics) |
| `session_id` | ❌ | Not present |
| `started_by` | ❌ | `created_by` |
| `created_at` | ❌ | `order_date` (different format) |
| `updated_at` | ❌ | `updated_date` |
| `typeof` | ❌ | Not present |

---

## 5. F&B Menu Items — `misc` Collection

### 5.1 Inventory (43 items, all under `KURO0001_002` / Madhapur cafe)

| Category | Items | Price Range (₹) | Total Stock |
|----------|-------|----------------|-------------|
| Cakes | 3 | 20–169 | 7 |
| Cheesy Shots | 1 | 3 | 4,930 |
| Chips | 5 | 40–50 | 41,927 |
| Chocolates | 3 | 30–40 | -27 |
| Cookies | 1 | 20 | 152 |
| Energy Drinks | 6 | 30–150 | 430 |
| French Fries | 1 | 159 | 7,799 |
| Noodles | 5 | 69–99 | 307 |
| Onion Rings | 1 | 199 | 194 |
| Paneer Roll | 1 | 120 | 1 |
| Pizza | 3 | 150–160 | 508 |
| Potato Shots | 2 | 149–169 | 33,340 |
| Samosa | 1 | 129 | 0 |
| Soft Drinks | 7 | 50–70 | 60,312 |
| Water | 3 | 10–20 | -571 |

**Negative stock items:** Chocolates (-27), Water (-571), Soft Drinks (-101). Inventory tracking is inconsistent.

### 5.2 Schema

```json
{
  "productid": "WATBAI2510000034",
  "collection": "beverage",
  "quantity": {"Madhapur": 1, "LB Nagar": 0},
  "total_quantity": 1,
  "type": "Water",
  "avgprice": 10,
  "maxprice": 10,
  "minprice": 10,
  "totalprice": 10,
  "stock": [{"invoiceid": "", "price": 7.5, "quantity": 48}],
  "sold": [],
  "active": true,
  "bgcode": "KURO0001",
  "division": "KURO0001_002",
  "branch_code": "KURO0001_002_002"
}
```

---

## 6. Gaming Collections — 12/13 Missing

| Collection | Purpose | kuropurchase | KungOS_Mongo_One |
|------------|---------|-------------|------------------|
| `presets` | Gaming presets | 6 | 6 | ✅ |
| `prods` | Products | 0 | 0 | ❌ |
| `builds` | PC builds | 0 | 0 | ❌ |
| `kgbuilds` | KG builds | 0 | 0 | ❌ |
| `custombuilds` | Custom builds | 0 | 0 | ❌ |
| `components` | PC components | 0 | 0 | ❌ |
| `accessories` | Accessories | 0 | 0 | ❌ |
| `monitors` | Monitors | 0 | 0 | ❌ |
| `networking` | Networking gear | 0 | 0 | ❌ |
| `external` | External products | 0 | 0 | ❌ |
| `games` | Game catalog | 0 | 0 | ❌ |
| `kurodata` | Kuro data | 0 | 0 | ❌ |
| `lists` | Product lists | 0 | 0 | ❌ |

**Deferred to Phase 3b per integration plan.** The `products` MongoDB database (which held this data) no longer exists.

---

## 7. Code-to-Database Reference Audit

### 7.1 Collections Referenced in New KungOS Code (`domains/`)

| Collection | In KungOS_Mongo_One? | Status |
|-----------|---------------------|--------|
| `accounts` | ✅ | OK |
| `estimates` | ✅ | OK |
| `indentpos` | ✅ | OK |
| `indentproduct` | ✅ | OK |
| `inwardinvoices` | ✅ (16 docs) | ⚠️ Near-empty |
| `inwardpayments` | ✅ | OK |
| `kgorders` | ✅ | OK |
| `misc` | ✅ | OK |
| `outwardinvoices` | ✅ | OK |
| `paymentvouchers` | ✅ | OK |
| `products` | ✅ | OK |
| `purchaseorders` | ✅ | OK |
| `reb_users` | ✅ | OK |
| `stock_register` | ✅ | OK |
| `tournaments` | ✅ | OK |
| `tourneyregister` | ✅ | OK |
| `tporders` | ✅ | OK |
| `vendors` | ✅ | OK |
| `asset_register` | ❌ | 🔴 Referenced in design, not in DB |
| `gamerDetails` | ❌ | 🔴 Dead reference |
| `gamers` | ❌ | 🔴 Dead reference |
| `rbpackages` | ❌ | 🔴 Dead reference |

### 7.2 Field Naming Violations

| File | Line | Issue |
|------|------|-------|
| `domains/cafe_fnb/gateways.py:153` | `'bgcode': bg_code` | Uses legacy `bgcode` instead of `bg_code` |
| `backend/utils.py` | `get_collection()` | Uses `bgcode` internally (matches DB field name — OK) |

**Note:** The DB field is `bgcode` (no underscore). The canonical naming convention (§11.6) says `bg_code`. The DB was **not** renamed — only the code convention was locked. This is a design debt item (Phase 5.7).

---

## 8. Cafe-FNB Integration Blockers

### 8.1 `OrderGateway` Assumptions That Don't Match Reality

| Assumption | Reality | Fix Needed |
|------------|---------|------------|
| `kgorders` has `items[]` | Has `food[]`, `service[]`, `builds[]` | Map to correct field names |
| `kgorders` has `total` | Has `totalprice` | Field rename |
| `kgorders` has `amount_paid` | Not tracked | Compute from `food[]` + `service[]` prices |
| `kgorders` has `payment_status` | Has `order_status` (different values) | Map semantics |
| `kgorders` has `session_id` | Not present | New linking strategy needed |
| `kgorders` has `started_by` | Has `created_by` | Field rename |
| `kgorders` has `created_at` | Has `order_date` (different format) | Format conversion |
| `kgorders` has `typeof` | Not present | Derive from `food[]` presence |
| `menu` queries `stock_register` | F&B items in `misc` | Change collection |
| `create()` writes new doc | Legacy appends `food[]` to existing order | Change write pattern |

### 8.2 Menu Endpoint

**Current:** `GET /cafe-fnb/menu` returns empty stub (queries `stock_register` — PC components only).

**Should query:** `misc` collection with filter:
```python
{'type': {'$in': FB_TYPES}, 'productid': {'$exists': True}, 'active': True}
```

Where `FB_TYPES = ['Cakes', 'Cheesy Shots', 'Chips', 'Chocolates', 'Cookies', 'Energy Drinks', 'French Fries', 'Noodles', 'Onion Rings', 'Paneer Roll', 'Pizza', 'Potato Shots', 'Samosa', 'Soft Drinks', 'Water']`

### 8.3 Session-Order Linking

The `Session.last_order_id` field references `kgorders.orderid`. But:
- `kgorders` has no `session_id` field (no reverse link)
- Food items are embedded in `kgorders.food[]` — not separate orders
- The legacy flow: food was added to the **gaming session's kgorder**, not a separate F&B order

**Options:**
1. **Add `session_id` to `kgorders`** — DB migration, adds field to 9,162 docs
2. **Use `created_by` as linking key** — `created_by` = phone number = `session.started_by`
3. **Create separate `fnb_orders` collection** — Clean separation, but breaks legacy flow
4. **Keep `last_order_id` as manual reference** — Staff enters order ID, no auto-linking

---

## 9. Risk Register

| Risk | Severity | Status | Mitigation |
|------|----------|--------|------------|
| `inwardinvoices` 99.7% data loss | 🔴 Critical | Open | Restore from production dump or `kuropurchase` |
| `entity` field missing in `kgorders` | 🟡 Medium | Open | Use `division` for filtering; legacy analytics code needs update |
| `misc` collection is catch-all | 🟡 Medium | Open | Consider splitting into dedicated collections |
| Negative stock in F&B items | 🟡 Medium | Open | Inventory reconciliation needed |
| `DUNE0003_001` has 0 documents | 🟠 High | Open | Verify migration split rebellion data correctly |
| 7 dead collection references | 🟡 Medium | Open | Remove dead code or create collections |
| `asset_register` referenced but missing | 🟡 Medium | Open | Create collection or remove references |
| Field naming: `bgcode` vs `bg_code` | 🟢 Low | Deferred (Phase 5.7) | DB migration required |
| Gaming collections 12/13 missing | 🟠 High | Deferred (Phase 3b) | Merge from `kuro-gaming-dj-backend` |
| Cafe-fnb gateway wrong assumptions | 🔴 Critical | Open | Rewrite gateway to match actual schema |

---

## 10. Recommendations (Prioritized)

### Immediate (Blockers)

1. **Restore `inwardinvoices`** — 4,610 documents missing. Restore from `kuropurchase` or production dump. This breaks all financial analytics.
2. **Fix `OrderGateway` schema mapping** — Gateway assumes fields that don't exist. Rewrite to match actual `kgorders` schema (`food[]`, `totalprice`, `created_by`, etc.).
3. **Fix menu endpoint** — Query `misc` collection instead of `stock_register`.

### Short-Term (Weeks 1-2)

4. **Verify `purchaseorders`/`inwardpayments` inflation** — Are the extra 21,000+ documents legitimate?
5. **Verify `DUNE0003_001` migration** — 0 documents despite tenant config.
6. **Clean dead collection references** — `gamerDetails`, `gamers`, `rbpackages`, `asset_register`.
7. **Decide on session-order linking** — See §8.3 options.

### Medium-Term (Weeks 3-6)

8. **Split `misc` collection** — 5,512 docs across 4 unrelated categories. Consider: `fb_menu` (F&B), `pc_components` (PC parts), `gaming_gear`, `accounting_categories`.
9. **Reconcile negative stock** — F&B items with negative `total_quantity`.
10. **Field naming migration** — `bgcode` → `bg_code` across all collections (Phase 5.7).
11. **Gaming collections** — Merge 12 missing collections from `kuro-gaming-dj-backend` (Phase 3b).

---

## Appendix A: Complete Collection Inventory (KungOS_Mongo_One)

| # | Collection | Docs | Div 001 | Div 002 | Indexes | bgcode idx |
|---|-----------|------|---------|---------|---------|-----------|
| 1 | `accounts` | 7 | 7 | 0 | 4 | ✅ |
| 2 | `bgData` | 1 | 1 | 0 | 4 | ✅ |
| 3 | `employee_attendance` | 966 | 966 | 0 | 6 | ✅ |
| 4 | `entities` | 2 | 1 | 1 | 3 | ✅ |
| 5 | `estimates` | 4,308 | 4,308 | 0 | 6 | ✅ |
| 6 | `indentpos` | 247 | 247 | 0 | 5 | ✅ |
| 7 | `indentproduct` | 1,490 | 1,490 | 0 | 4 | ✅ |
| 8 | `inwardcreditnotes` | 106 | 106 | 0 | 5 | ✅ |
| 9 | `inwarddebitnotes` | 3 | 3 | 0 | 5 | ✅ |
| 10 | `inwardinvoices` | **16** | 16 | 0 | 6 | ✅ |
| 11 | `inwardpayments` | 21,026 | 19,980 | 1,046 | 6 | ✅ |
| 12 | `kgorders` | 9,162 | 9,162 | 0 | 6 | ✅ |
| 13 | `misc` | 5,512 | 1,752 | 3,760 | 4 | ✅ |
| 14 | `outward` | 754 | 545 | 209 | 5 | ✅ |
| 15 | `outwardcreditnotes` | 150 | 150 | 0 | 5 | ✅ |
| 16 | `outwarddebitnotes` | 13 | 13 | 0 | 5 | ✅ |
| 17 | `outwardinvoices` | 1,165 | 1,165 | 0 | 6 | ✅ |
| 18 | `paymentvouchers` | 3,459 | 3,459 | 0 | 6 | ✅ |
| 19 | `players` | 117 | 0 | 117 | 4 | ✅ |
| 20 | `presets` | 6 | 6 | 0 | 4 | ✅ |
| 21 | `products` | 82 | 0 | 82 | 7 | ✅ |
| 22 | `purchaseorders` | 15,216 | 15,216 | 0 | 7 | ✅ |
| 23 | `reb_users` | 1,982 | 0 | 1,982 | 5 | ✅ |
| 24 | `serviceRequest` | 1,625 | 1,625 | 0 | 6 | ✅ |
| 25 | `stock_register` | 194 | 194 | 0 | 4 | ✅ |
| 26 | `teams` | 14 | 14 | 0 | 4 | ✅ |
| 27 | `tournaments` | 3 | 0 | 3 | 4 | ✅ |
| 28 | `tourneyregister` | 56 | 0 | 56 | 4 | ✅ |
| 29 | `tpbuilds` | 123 | 123 | 0 | 6 | ✅ |
| 30 | `tporders` | 229 | 229 | 0 | 6 | ✅ |
| 31 | `vendors` | 409 | 409 | 0 | 7 | ✅ |
| | **Total** | **68,443** | **61,187** | **7,256** | | |

## Appendix B: Legacy Code Collection References (`kteam-dj-be-main`)

| Collection | File | Line | Operation |
|-----------|------|------|-----------|
| `accounts` | `kurostaff/views.py:507` | find | sundrycreditors |
| `bgData` | (indirect) | — | BG metadata |
| `employee_attendance` | (indirect) | — | HR |
| `estimates` | `kurostaff/views.py:203` | find | List estimates |
| `gamerDetails` | `rebellion/views.py:264` | find | ❌ Dead |
| `gamers` | `rebellion/views.py:274-442` | find/insert/update | ❌ Dead |
| `indentpos` | `kurostaff/views.py` | find | Procurement |
| `indentproduct` | `kurostaff/views.py` | find | Procurement |
| `inwardCreditNotes` | (indirect) | — | Finance |
| `inwardDebitNotes` | (indirect) | — | Finance |
| `inwardInvoices` | (indirect) | — | Finance |
| `inwardpayments` | `rebellion/views.py:472,784,790,850` | find/update/insert | Payments |
| `kgorders` | `rebellion/views.py:468,624-631,728,797,801,849` | find/update/insert | Orders |
| `kurodata` | (indirect) | — | ❌ Dead |
| `media` | (indirect) | — | ❌ Dead |